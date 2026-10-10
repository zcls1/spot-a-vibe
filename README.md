# spot-a-vibe
Knight Hacks IX

Step in front of your laptop camera and spot-a-vibe guesses your music taste. When it sees someone, it counts down and snaps a photo (or press **Capture** to snap one right away), then asks [Cloudflare's Clef-Flash](https://huggingface.co/Cloudflare/clef-flash) model which genre fits their style (clothes and accessories only, never height, race or weight).

The result appears under the camera as "Your vibe is": the top genre, how confident the model is, and a ranked breakdown across all nine genres (Pop, Rock, Metal, Rap, R&B, Country, Electronic, EDM and Jazz). With Spotify connected, it also shows songs for that genre that can be saved as a playlist.

Person detection runs entirely in the browser with [OpenCV.js](https://docs.opencv.org/4.9.0/opencv.js) and a MobileNet-SSD object detector. Only the snapshots are sent to the Flask server for genre detection.

## Run

The Flask server serves the page and runs genre detection with [Clef-Flash](https://huggingface.co/Cloudflare/clef-flash), loaded directly with PyTorch. The model is ~19 GB (9.4B parameters, bf16), so you need a machine with an NVIDIA GPU or an Apple Silicon Mac with enough memory (tested on an M3 Max with 36 GB).

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r endpoint/requirements.txt
python server.py            # serves http://127.0.0.1:8000
```

The first run downloads the model (~19 GB). Startup then takes about a minute: loading the weights, plus one warm-up pass so the first snapshot isn't slow. On an M3 Max each snapshot takes about 2 seconds after that. The device is picked automatically (CUDA, then Apple GPU, then CPU); override it with `CLEF_DEVICE`.

To work on the front end without the model, `CLEF_STUB=1 python server.py` skips it and returns random genre probabilities. That only needs `requirements.txt`.

Camera access requires a secure context, so open the page via `localhost` or HTTPS, not `file://`.

## Deploy

The deployment has two parts: the model runs on a GPU [Hugging Face Inference Endpoint](https://huggingface.co/docs/inference-endpoints), and the web server (a small CPU container) serves the page and forwards snapshots to it. Keeping the two apart means changes to the web server never require rebuilding or restarting the GPU.

### Model endpoint

1. Duplicate [`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash) (Apache-2.0) into your account, then add `endpoint/handler.py` and `endpoint/requirements.txt` to the root of your copy.
2. Create an Inference Endpoint from your copy with a GPU that has at least 24 GB of memory; one with 48 GB (e.g. L40S) leaves headroom. Leave it protected so only your token can call it, and enable scale-to-zero to save money between demos.
3. The endpoint takes an image body (`Content-Type: image/png` or `image/jpeg`) and returns the same response as `POST /api/genre`.

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
| `HF_TOKEN` | a Hugging Face token that can call the endpoint |
| `SECRET_KEY` | random string that signs session cookies; required when Spotify is configured |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | from the Spotify developer dashboard |
| `SPOTIFY_REDIRECT_URI` | `https://<your host>/spotify/callback`, also registered in the dashboard |

Health checks can use `GET /healthz`. If the endpoint has scaled to zero, the first snapshot returns "the model is waking up" while it starts.

### Spotify

Connect a Spotify account with the **Connect Spotify** bar above the camera. Sign-in opens in a popup, so the camera and the current vibe stay put, and songs for that vibe load as soon as the popup closes. If the browser blocks popups, the page goes to Spotify itself instead; the current vibe is kept in `sessionStorage` and shown again on the way back, but the camera needs starting again. After that, every new vibe shows song cards (album art, title, artist, linking to Spotify) for its top genre, and **Save playlist to Spotify** saves them as a private playlist on that account. One account is connected at a time; **Disconnect** lets another one sign in.

- **Sign-in:** `/spotify/login` signs the user in (with `?popup=1`, the callback answers with a page that tells the opener it's done and closes, instead of redirecting to `/`) (Authorization Code flow, with permission to create playlists), and `/api/spotify/status` reports whether they are connected. Tokens are kept in the signed session cookie and refreshed automatically.
- **Songs:** `POST /api/playlist/songs` with `{"genre": "Jazz"}` searches Spotify for tracks in that genre (`genre:"jazz"`), collects the top 50 results (in pages of 10, the most Spotify allows per search), drops repeats of the same song, and picks 10 at random, so the same genre gives different songs each time.
- **Saving:** `POST /api/playlist` with `{"genre": "Jazz", "uris": [...]}` saves exactly those tracks to a new playlist called "spot-a-vibe: Jazz" (`spotify_service.py`).
- **Development mode:** until the Spotify app has extended quota, it only works for up to 5 Spotify accounts on the app's allowlist (Developer Dashboard → your app → Settings → User Management), and the app owner needs Spotify Premium.

For local runs, the variables can go in a `.env` file instead of the environment.

## How it works

### Genre detection

- Each snapshot is uploaded to `POST /api/genre`. The server checks it with Pillow and runs it through Clef-Flash (`endpoint/handler.py`, either locally or on the Inference Endpoint) as a Jev/SystemOne `choice` question over the 9 genres, asking it to judge only clothing and accessories.
- The answer comes back with a probability for every genre. The result under the camera shows the top genre, its confidence and, under "Full breakdown", a ranked bar for each genre; each snapshot in the gallery is labelled with its genre too (hover for the full breakdown).
- If Spotify is connected, song cards for the newest result's top genre follow, with a button to save them as a playlist (see [Spotify](#spotify)). **Scan again** runs the countdown for a fresh snapshot.
- Before a result, the same spot shows the current stage: waiting, countdown, "Reading the vibe…" while the model runs, then the result, or the error if the model fails. If several snapshots are in flight, only the newest result is shown.

### Spotting a person

- `detector.worker.js` loads OpenCV.js and `models/MobileNetSSD_deploy.*` (a Caffe SSD trained on PASCAL VOC) in a Web Worker, so the ~0.5–1 s inference doesn't freeze the page.
- Each frame is resized to 300×300 and run through the network; only "person" detections above the confidence threshold (the Sensitivity slider) and covering at least 4% of the frame are kept. That excludes people far away in the background.
- Because it detects whole people, not faces, it still works if you're facing away, looking down, or only partly in frame.
- Presence is debounced: 3 consecutive detections → **present**; nobody detected for the "Away after" grace period → **away**.
- When someone arrives, a 3-second countdown appears over the video, then a full-resolution snapshot (mirrored like the preview, without detection boxes) is added to the Snapshots gallery; click one to download it. Leaving before the countdown ends cancels it, and only one snapshot is taken per arrival.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
