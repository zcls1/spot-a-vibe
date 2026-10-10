"""Flask server for spot-a-vibe.

Serves the static app, exposes POST /api/genre for genre detection, and lets a
user sign in with Spotify to get songs for their genre (POST /api/playlist/songs)
and save them as a playlist on their account (POST /api/playlist). Genre
detection runs in one of three places:

  - a Hugging Face Inference Endpoint (CLEF_ENDPOINT_URL set): the snapshot is
    forwarded there, so this server needs no GPU or model dependencies
  - a stub (CLEF_STUB=1) that returns random probabilities, for working on the
    front end
  - otherwise locally, with endpoint/handler.py (needs endpoint/requirements.txt)

Environment variables:
  CLEF_ENDPOINT_URL      URL of the Inference Endpoint running endpoint/handler.py
  HF_TOKEN               Hugging Face token allowed to call that endpoint
  CLEF_STUB              set to 1 to skip the model and return random probabilities
  SECRET_KEY             signs the session cookie that holds Spotify tokens
  SPOTIFY_CLIENT_ID      from the Spotify developer dashboard
  SPOTIFY_CLIENT_SECRET
  SPOTIFY_REDIRECT_URI   must match a redirect URI registered in the dashboard,
                         e.g. https://<host>/spotify/callback
Variables can also be set in a .env file, which spotify_service loads on import.
Local model runs also read CLEF_MODEL, CLEF_REVISION and CLEF_DEVICE (see
endpoint/handler.py).
"""

import io
import logging
import os
import random
import re
import secrets
import time
from urllib.parse import urlencode

import requests
from flask import Flask, abort, jsonify, redirect, request, send_from_directory, session
from PIL import Image, UnidentifiedImageError

from endpoint.handler import GENRES, SUBGENRES
# Imported before reading the environment below, since it loads .env.
from spotify_service import TOKEN_URL, create_playlist, search_songs

ENDPOINT_URL = os.environ.get("CLEF_ENDPOINT_URL")
HF_TOKEN = os.environ.get("HF_TOKEN")
STUB = os.environ.get("CLEF_STUB") == "1"

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI")
SPOTIFY_SCOPES = "playlist-modify-private playlist-modify-public"

app = Flask(__name__, static_folder=None)
app.logger.setLevel(logging.INFO)
# Snapshots are full-resolution frames; a few MB is plenty.
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
# A random key works for one process, but gunicorn workers each need the same key.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
ROOT = os.path.dirname(os.path.abspath(__file__))

local_model = None


class EndpointError(Exception):
    """A genre detection failure whose message is safe to show on the page."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def stub_choice(options):
    weights = {option: random.random() ** 3 for option in options}
    total = sum(weights.values())
    probabilities = {option: round(w / total, 4) for option, w in weights.items()}
    choice = max(probabilities, key=probabilities.get)
    return {"type": "choice", "choice": choice, "confidence": probabilities[choice], "probabilities": probabilities}


def stub_answer():
    genre = stub_choice(GENRES)
    return {
        "model": "stub",
        "answers": {"genre": genre, "subgenre": stub_choice(SUBGENRES[genre["choice"]])},
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def classify_remote(data, content_type):
    try:
        res = requests.post(
            ENDPOINT_URL,
            data=data,
            headers={"Content-Type": content_type, **({"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {})},
            timeout=120,
        )
    except requests.RequestException:
        app.logger.exception("could not reach the inference endpoint")
        raise EndpointError("could not reach the model")
    # A scaled-to-zero endpoint answers 503 while it starts up and loads the weights.
    if res.status_code == 503:
        raise EndpointError("the model is waking up, try again in a minute", status=503)
    if not res.ok:
        app.logger.error("inference endpoint returned %s: %s", res.status_code, res.text[:500])
        raise EndpointError("the model failed to read this snapshot")
    return res.json()


@app.post("/api/genre")
def genre():
    upload = request.files.get("image")
    if upload is None:
        return jsonify(error="expected an image file in the 'image' form field"), 400
    data = upload.read()
    try:
        # Decode the snapshot with Pillow, both to reject anything that isn't an image and
        # to get an RGB copy for the local model. convert() forces the full decode.
        image = Image.open(io.BytesIO(data))
        content_type = Image.MIME.get(image.format, "image/png")
        image = image.convert("RGB")
    except UnidentifiedImageError:
        return jsonify(error="could not read the uploaded image"), 400
    try:
        if STUB:
            return jsonify(stub_answer())
        if ENDPOINT_URL:
            return jsonify(classify_remote(data, content_type))
        return jsonify(local_model.classify(image))
    except EndpointError as err:
        return jsonify(error=str(err)), err.status
    except Exception:
        app.logger.exception("genre classification failed")
        return jsonify(error="the model failed to read this snapshot"), 500


# --- Spotify ------------------------------------------------------------------
# Authorization Code flow: /spotify/login sends the user to Spotify, which sends them
# back to /spotify/callback with a code that we exchange for tokens. The tokens live
# in the signed session cookie, so there is no database.


def spotify_configured():
    return all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI])


if spotify_configured() and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("set SECRET_KEY so Spotify sessions survive restarts and work across workers")


def spotify_token_request(form):
    res = requests.post(
        TOKEN_URL,
        data=form,
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10,
    )
    res.raise_for_status()
    tokens = res.json()
    session["spotify"] = {
        "access_token": tokens["access_token"],
        # Spotify only sometimes sends a new refresh token; keep the old one otherwise.
        "refresh_token": tokens.get("refresh_token") or session.get("spotify", {}).get("refresh_token"),
        "expires_at": time.time() + tokens["expires_in"] - 60,
    }


def spotify_access_token():
    """The signed-in user's access token, refreshed if it has expired, or None."""
    tokens = session.get("spotify")
    if not tokens:
        return None
    if time.time() >= tokens["expires_at"]:
        try:
            spotify_token_request({"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
        except requests.RequestException:
            app.logger.exception("could not refresh the Spotify token")
            session.pop("spotify", None)
            return None
    return session["spotify"]["access_token"]


@app.get("/spotify/login")
def spotify_login():
    if not spotify_configured():
        return jsonify(error="Spotify is not configured on this server"), 503
    session["spotify_state"] = secrets.token_urlsafe(16)
    # The page opens sign-in in a popup so the camera keeps running; see spotify_callback.
    session["spotify_popup"] = request.args.get("popup") == "1"
    return redirect("https://accounts.spotify.com/authorize?" + urlencode({
        "response_type": "code",
        "client_id": SPOTIFY_CLIENT_ID,
        "scope": SPOTIFY_SCOPES,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "state": session["spotify_state"],
        # Always show Spotify's dialog, so after disconnecting, a different account can sign in.
        "show_dialog": "true",
    }))


@app.get("/spotify/callback")
def spotify_callback():
    # The state check stops another site from signing the user in to its own account.
    if not request.args.get("state") or request.args.get("state") != session.pop("spotify_state", None):
        abort(400)
    if "code" in request.args:
        try:
            spotify_token_request({
                "grant_type": "authorization_code",
                "code": request.args["code"],
                "redirect_uri": SPOTIFY_REDIRECT_URI,
            })
        except requests.RequestException:
            app.logger.exception("Spotify token exchange failed")
    # If the user declined, Spotify sends ?error=access_denied; they just stay signed out.
    if session.pop("spotify_popup", False):
        return SPOTIFY_POPUP_DONE
    return redirect("/")


# Returned to the sign-in popup: tells the page that opened it to re-check its Spotify
# status, then closes. The message carries no data, so the page trusts only the server.
SPOTIFY_POPUP_DONE = """<!doctype html>
<meta charset="utf-8">
<title>spot-a-vibe</title>
<p>You can close this window and go back to spot-a-vibe.</p>
<script>
  if (window.opener) {
    window.opener.postMessage("spotify-sign-in-done", location.origin);
    window.close();
  } else {
    location.replace("/");
  }
</script>
"""


@app.post("/spotify/logout")
def spotify_logout():
    session.pop("spotify", None)
    return jsonify(connected=False)


# A Spotify track URI, as returned by search_songs.
TRACK_URI = re.compile(r"spotify:track:[A-Za-z0-9]{22}")


def spotify_genre_request(handler):
    """Checks the genre and sign-in shared by the playlist routes, then calls
    handler(token, genre, data) and turns Spotify failures into errors for the page."""
    data = request.get_json(silent=True) or {}
    genre = data.get("genre")
    if genre not in GENRES:
        return jsonify(error=f"genre must be one of {', '.join(GENRES)}"), 400
    token = spotify_access_token()
    if token is None:
        return jsonify(error="connect Spotify first"), 401
    try:
        return handler(token, genre, data)
    except requests.HTTPError as err:
        app.logger.exception("Spotify request failed")
        if err.response.status_code == 401:
            # The user revoked access or the token is no longer valid; sign them out.
            session.pop("spotify", None)
            return jsonify(error="Spotify sign-in expired, connect again"), 401
        if err.response.status_code == 403:
            # Development-mode apps only work for accounts on the app's allowlist.
            return jsonify(error="this Spotify account isn't allowed to use the app yet"), 403
        return jsonify(error="Spotify request failed"), 502
    except requests.RequestException:
        app.logger.exception("could not reach Spotify")
        return jsonify(error="could not reach Spotify"), 502


@app.post("/api/playlist/songs")
def playlist_songs():
    def find(token, genre, data):
        # Clef's probability for each of the genre's sub-genres steers which artists are
        # picked. Without them (e.g. an endpoint still running the one-pass handler), or
        # if they're malformed, every sub-genre counts equally.
        probabilities = data.get("subgenres")
        if not (
            isinstance(probabilities, dict)
            and set(probabilities) <= set(SUBGENRES[genre])
            and all(isinstance(p, (int, float)) and 0 <= p <= 1 for p in probabilities.values())
            and any(probabilities.values())
        ):
            probabilities = {subgenre: 1.0 for subgenre in SUBGENRES[genre]}
        songs = search_songs(token, genre, probabilities)
        if not songs:
            return jsonify(error=f"Spotify found no {genre} songs"), 404
        return jsonify(genre=genre, songs=songs)

    return spotify_genre_request(find)


@app.post("/api/playlist")
def save_playlist():
    def save(token, genre, data):
        # Save exactly the songs the page showed; searching again would pick different ones.
        uris = data.get("uris")
        if not isinstance(uris, list) or not 0 < len(uris) <= 100 or not all(
            isinstance(uri, str) and TRACK_URI.fullmatch(uri) for uri in uris
        ):
            return jsonify(error="uris must be a list of 1 to 100 Spotify track URIs"), 400
        # Name the playlist after the sub-genre when the page knows it.
        subgenre = data.get("subgenre")
        name = subgenre if subgenre in SUBGENRES[genre] else genre
        return jsonify(genre=genre, playlist=create_playlist(token, name, uris))

    return spotify_genre_request(save)


@app.get("/api/spotify/status")
def spotify_status():
    return jsonify(configured=spotify_configured(), connected=spotify_access_token() is not None)


# --- Static files and health ----------------------------------------------------


@app.get("/healthz")
def healthz():
    return jsonify(ok=True)


# Only the front end is served, not server.py or anything else in the repo.
PUBLIC_FILES = {"index.html", "app.js", "style.css", "detector.worker.js"}


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    if filename in PUBLIC_FILES or filename.startswith("models/"):
        return send_from_directory(ROOT, filename)
    return jsonify(error="not found"), 404


if not STUB and not ENDPOINT_URL:
    from endpoint.handler import EndpointHandler

    local_model = EndpointHandler()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=False)
