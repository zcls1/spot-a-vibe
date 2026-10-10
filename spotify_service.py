# Import os to read environment variables
import os

# Import time to know when the cached token expires
import time

# Import requests to communicate with Spotify
import requests

# Import HTTPBasicAuth to authenticate with Spotify
from requests.auth import HTTPBasicAuth

# Import the function that loads credentials from .env
from dotenv import load_dotenv

# Load the private Spotify credentials from the .env file
load_dotenv()

# Spotify's URL for requesting an access token
TOKEN_URL = "https://accounts.spotify.com/api/token"

# Spotify's URL for searching songs
SEARCH_URL = "https://api.spotify.com/v1/search"

# The current access token and when it expires, so we don't ask for a new one every search
_token = {"value": None, "expires_at": 0}


def get_spotify_token():
    # Reuse the cached token until a minute before it expires
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]

    # Read the Spotify Client ID from the environment
    client_id = os.getenv("SPOTIFY_CLIENT_ID")

    # Read the Spotify Client Secret from the environment
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    # Stop if either credential is missing
    if not client_id or not client_secret:
        raise RuntimeError("Spotify credentials are missing.")

    # Request an access token using the client credentials
    response = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=HTTPBasicAuth(client_id, client_secret),
        timeout=15,
    )

    # Raise an error if Spotify rejects the request
    response.raise_for_status()

    # Remember the token and when it expires (Spotify gives the lifetime in seconds)
    body = response.json()
    _token["value"] = body["access_token"]
    _token["expires_at"] = time.time() + body["expires_in"] - 60

    # Return the access token from Spotify's response
    return _token["value"]


def search_songs(tags, limit=10):
    # Get an access token before searching
    token = get_spotify_token()

    # Combine the tags into one search phrase
    # Example: ["dreamy", "pop"] becomes "dreamy pop"
    query = " ".join(tags)

    # Send a song-search request to Spotify
    response = requests.get(
        SEARCH_URL,

        # Include the access token to authorize the request
        headers={"Authorization": f"Bearer {token}"},

        # Tell Spotify what to search for and how many results to return
        params={
            "q": query,
            "type": "track",
            "limit": limit,
        },

        # Stop waiting if Spotify takes too long
        timeout=15,
    )

    # Raise an error if the search request fails
    response.raise_for_status()

    # Extract the list of matching tracks from the response
    tracks = response.json()["tracks"]["items"]

    # Build a simpler list containing only the information we need
    return [
        {
            # Get the song's title
            "title": track["name"],

            # Combine all artist names into one string
            "artist": ", ".join(
                artist["name"] for artist in track["artists"]
            ),

            # Get the album cover if one is available
            "album_art": (
                track["album"]["images"][0]["url"]
                if track["album"]["images"]
                else None
            ),

            # Get the link to the song on Spotify
            "spotify_url": track["external_urls"].get("spotify"),

            # Get the Spotify track ID
            "track_id": track["id"],
        }

        # Repeat these steps for every matching song
        for track in tracks
    ]