# spot-a-vibe
Knight Hacks IX

Step in front of your laptop camera and spot-a-vibe guesses your music taste. When it sees someone, it counts down and snaps a photo (or press **Capture** to snap one right away), then asks [Cloudflare's Clef-Flash](https://huggingface.co/Cloudflare/clef-flash) model which genre fits their style. The result appears under the camera as "Your vibe is": the top genre, how confident the model is, and a ranked breakdown across all nine genres: Pop, Rock, Metal, Rap, R&B, Country, Electronic, EDM and Jazz. With Spotify connected, it also suggests songs for the vibe that can be saved as a playlist.

Person detection runs entirely in the browser with [OpenCV.js](https://docs.opencv.org/4.9.0/opencv.js) and a MobileNet-SSD object detector. Only the snapshots are sent to the Flask server for genre detection.

## Run

The Flask server serves the page and runs genre detection with [Clef-Flash](https://huggingface.co/Cloudflare/clef-flash), loaded directly with PyTorch. 

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r endpoint/requirements.txt
python server.py            # serves http://127.0.0.1:8000
```

The first run downloads the model (~19 GB). Startup then takes about a minute: loading the weights, plus one warm-up pass so the first snapshot isn't slow. To work on the front end without the model, `CLEF_STUB=1 python server.py` skips it and returns random genre probabilities; that only needs `requirements.txt`.

Open the page at http://127.0.0.1:8000. Camera access requires a secure context (`127.0.0.1`, `localhost` or HTTPS, not `file://`), and Spotify sign-in only works at the exact address registered with Spotify, so use `127.0.0.1` rather than `localhost`.

## Deploy

The deployment has two parts: the model runs on a GPU [Hugging Face Inference Endpoint](https://huggingface.co/docs/inference-endpoints), and the web server (a small CPU container) serves the page and forwards snapshots to it. Keeping the two apart means changes to the web server never require rebuilding or restarting the GPU.

### Model endpoint

The endpoint only needs the handler: when its repo doesn't contain the model, `handler.py` downloads [`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash) (Apache-2.0) at startup, pinned to a tested commit (`CLEF_REVISION`). So there's no need to copy the 19 GB model.

1. Put the handler in a small model repo of your own:
   ```sh
   hf auth login
   hf repos create <you>/spot-a-vibe-clef --private
   hf upload <you>/spot-a-vibe-clef endpoint/ .
   ```
2. On [endpoints.huggingface.co](https://endpoints.huggingface.co), create an endpoint from that repo with a GPU that has at least 24 GB of memory; one with 48 GB (e.g. L40S) leaves headroom. Use the default container (it picks up `handler.py` and installs `requirements.txt`), leave it **Protected** so only your token can call it, and set min replicas to 0 (scale-to-zero) to save money between demos. The first start takes several minutes while it downloads the weights; the Logs tab shows progress.
3. The endpoint takes an image body (`Content-Type: image/png` or `image/jpeg`) and returns the same response as `POST /api/genre`. To test it:
   ```sh
   curl -X POST "$CLEF_ENDPOINT_URL" -H "Authorization: Bearer $HF_TOKEN" \
     -H "Content-Type: image/jpeg" --data-binary @photo.jpg
   ```

Billing is per minute while the endpoint is running. Before a demo, resume it (or send one request) a few minutes early, since waking from zero takes a while.

### Web server

The `Dockerfile` builds the web server only, with no model dependencies, so it runs on any container host or VM without a GPU. It listens on `$PORT` (default 8000). Serve it over HTTPS at a stable URL: the camera only works in a secure context, and Spotify redirects back to a fixed address. Most hosts provide both; on a plain VM, put a reverse proxy such as Caddy or nginx in front.

```sh
docker build -t spot-a-vibe .
docker run -p 8000:8000 --env-file .env spot-a-vibe
```

Configure it with:

| Variable | |
| --- | --- |
| `CLEF_ENDPOINT_URL` | URL of the Inference Endpoint |
| `HF_TOKEN` | a fine-grained Hugging Face token allowed to call Inference Endpoints |
| `SECRET_KEY` | random string that signs session cookies; required when Spotify is configured |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | from the Spotify developer dashboard |
| `SPOTIFY_REDIRECT_URI` | `https://<your host>/spotify/callback`, also registered in the dashboard |

Health checks can use `GET /healthz`. If the endpoint has scaled to zero, the first snapshot returns "the model is waking up" while it starts.

### Spotify

Spotify needs an app registered once by the developer; people using the page then sign in with their own Spotify accounts.

1. At [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), **Create app**. Add the redirect URI `http://127.0.0.1:8000/spotify/callback` (Spotify rejects `localhost`), plus `https://<your host>/spotify/callback` for a deployment, and tick **Web API**.
2. In the app's **Settings**, copy the Client ID and client secret into `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`, and set `SPOTIFY_REDIRECT_URI` to the matching callback. Set `SECRET_KEY` to a random string, e.g. from `python3 -c "import secrets; print(secrets.token_hex(32))"`.
3. Under **Settings → User Management**, add every Spotify account that will sign in (see development mode below).
4. Restart the server. Until these are set, the bar above the camera says Spotify isn't set up.

Connect a Spotify account with the **Connect Spotify** bar above the camera. Sign-in opens in a popup, so the camera and the current vibe stay put, and songs for that vibe load as soon as the popup closes. If the browser blocks popups, the page goes to Spotify itself instead; the current vibe is kept in `sessionStorage` and shown again on the way back, but the camera needs starting again. After that, every new vibe shows song cards (album art, title, artist, linking to Spotify) picked to match it, and **Save playlist to Spotify** saves them as a private playlist on that account. One account is connected at a time; **Disconnect** lets another one sign in.

- **Sign-in:** `/spotify/login` signs the user in (Authorization Code flow, with permission to create playlists), and `/api/spotify/status` reports whether they are connected. With `?popup=1`, as the page uses it, the callback answers with a page that tells the opener it's done and closes, instead of redirecting to `/`. Tokens are kept in the signed session cookie and refreshed automatically.
- **Songs:** `POST /api/playlist/songs` with `{"genre": "Rap", "probabilities": {...}}` (Clef's probability for each genre) picks songs by well-known artists, so they're recognisable; Spotify no longer tells apps how popular a song is. `genre_artists.py` lists about 15 artists per genre, each with how much of their sound belongs to each genre (Drake is 60% Rap, 30% R&B, 10% Pop). Each artist is scored by how well that matches the vibe, and 5 are drawn at random weighted by that score: a confident Rap vibe mostly picks pure rap artists, while a Rap/R&B split brings in artists who cross both. Each one contributes 2 songs from their top 5 search results. If an artist search comes up short, the rest is filled from the genre's top 50 search results (`genre:"rap"`).
- **Saving:** `POST /api/playlist` with `{"genre": "Jazz", "uris": [...]}` saves exactly those tracks to a new playlist called "spot-a-vibe: Jazz" (`spotify_service.py`).
- **Development mode:** until the Spotify app has extended quota, it only works for up to 5 Spotify accounts on the app's allowlist (Developer Dashboard → your app → Settings → User Management), and the app owner needs Spotify Premium.

For local runs, the variables can go in a `.env` file instead of the environment.

## How it works

### Genre detection

- Each snapshot is uploaded to `POST /api/genre`. The server checks it with Pillow and runs it through Clef-Flash (`endpoint/handler.py`, either locally or on the Inference Endpoint) as a Jev/SystemOne `choice` question over the 9 genres, asking it to judge only clothing and accessories.
- The answer comes back with a probability for every genre. The result under the camera shows the top genre, its confidence and, under "Full breakdown", a ranked bar for each genre; each snapshot in the gallery is labelled with its genre too (hover for the full breakdown).
- If Spotify is connected, song cards picked to match the newest result's genre probabilities follow, with a button to save them as a playlist (see [Spotify](#spotify)). **Scan again** runs the countdown for a fresh snapshot.
- Before a result, the same spot shows the current stage: waiting, countdown, "Reading the vibe…" while the model runs, then the result, or the error if the model fails. If several snapshots are in flight, only the newest result is shown.

### Spotting a person

- `detector.worker.js` loads OpenCV.js and `models/MobileNetSSD_deploy.*` (a Caffe SSD trained on PASCAL VOC) in a Web Worker, so the ~0.5–1 s inference doesn't freeze the page.
- Each frame is resized to 300×300 and run through the network; only "person" detections above the confidence threshold (the Sensitivity slider) and covering at least 4% of the frame are kept. That excludes people far away in the background.
- Because it detects whole people, not faces, it still works if you're facing away, looking down, or only partly in frame.
- Presence is debounced: 3 consecutive detections → **present**; nobody detected for the "Away after" grace period → **away**.
- When someone arrives, a 3-second countdown appears over the video, then a full-resolution snapshot (mirrored like the preview, without detection boxes) is added to the Snapshots gallery; click one to download it. Leaving before the countdown ends cancels it, and only one snapshot is taken per arrival.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
