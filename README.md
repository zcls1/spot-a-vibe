# spot-a-vibe
Knight Hacks IX

Step in front of your laptop camera and spot-a-vibe guesses your music taste. When it sees someone, it counts down and snaps a photo (or press **Capture** to snap one right away), then asks [Cloudflare's Clef-Flash](https://huggingface.co/Cloudflare/clef-flash) model which genre fits their style, then asks it again which style of that genre fits best. The page then switches to "Your vibe is": the top genre and sub-genre (e.g. Rap · Trap), how confident the model is, and a ranked breakdown across all nine genres (Pop, Rock, Metal, Rap, R&B, Country, Electronic, EDM and Jazz) and the five sub-genres of the top one. With Spotify connected, it also suggests songs for the vibe that can be saved as a playlist.

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
3. The endpoint takes an image body (`Content-Type: image/png` or `image/jpeg`) and returns the same response as `POST /api/genre`, with both the genre and sub-genre answers. After changing `endpoint/handler.py`, upload it to the endpoint's repo again and restart the endpoint. To test it:
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

- **Sign-in:** `/spotify/login` signs the user in (Authorization Code flow, with permission to create playlists), and `/api/spotify/status` reports whether they are connected. With `?popup=1`, as the page uses it, the callback answers with a page that tells the opener it's done and closes, instead of redirecting to `/`. Tokens are kept in the signed session cookie and refreshed automatically.
- **Songs:** `POST /api/playlist/songs` with `{"genre": "Rap", "subgenres": {...}}` (Clef's probability for each of the genre's sub-genres) picks songs by well-known artists, so they're recognisable; Spotify no longer tells apps how popular a song is. `subgenre_artists.py` lists 5 artists per sub-genre. 5 artists are drawn at random, each weighted by their sub-genre's probability: with Trap at 0.8, about three quarters of the artists are trap artists, while a Trap/Pop Rap split mixes both. Each one contributes 2 songs from their top 5 search results. If an artist search comes up short, the rest is filled from the genre's top 50 search results (`genre:"rap"`). Without sub-genre probabilities (an endpoint still running the one-pass handler), every sub-genre counts equally.
- **Saving:** `POST /api/playlist` with `{"genre": "Jazz", "subgenre": "Bebop", "uris": [...]}` saves exactly those tracks to a new playlist named after the sub-genre, e.g. "spot-a-vibe: Bebop" (or the genre, without one) (`spotify_service.py`).
- **Development mode:** until the Spotify app has extended quota, it only works for up to 5 Spotify accounts on the app's allowlist (Developer Dashboard → your app → Settings → User Management), and the app owner needs Spotify Premium.

For local runs, the variables can go in a `.env` file instead of the environment.

## How it works

### Screens

`index.html` has three screens, one shown at a time, each with its own address so the browser's back button moves between them:

- **Welcome** (`/`): what spot-a-vibe does and how to get started, with a **Start Here!** bar at the bottom. The step tiles are placeholders for photos of each step.
- **Scan** (`#scan`): the camera, **Capture**, the Spotify bar, the snapshot gallery and the detector settings. The line under the camera shows the current stage: waiting, countdown, "Reading the vibe…" while the model runs, or the error if the model fails.
- **Your vibe** (`#vibe`): opens once Clef has read the newest snapshot. It shows the genre and sub-genre, the breakdown, songs to match, **Save playlist to Spotify** and **Scan Again**, which goes back to the camera and starts a countdown.

The camera keeps running across screens, but snapshots are only taken automatically on the scan screen, so someone walking past while a result is showing doesn't trigger a new scan.

### Genre detection

- Each snapshot is uploaded to `POST /api/genre`. The server checks it with Pillow and runs it through Clef-Flash (`endpoint/handler.py`, either locally or on the Inference Endpoint) as a Jev/SystemOne `choice` question over the 9 genres, asking it to judge only clothing and accessories.
- A second pass then asks a `choice` question over the top genre's 5 sub-genres (`SUBGENRES` in `endpoint/handler.py`), each described in a few words so the model knows the style. Both answers come back in one response, as `answers.genre` and `answers.subgenre`, so this doubles the model time per snapshot. The sub-genres were picked to differ in look as well as sound, since the model only sees the image:

| Genre | Sub-genres |
| --- | --- |
| Pop | Dance Pop, Alt Pop, Singer-Songwriter Pop, K-Pop, Synth-pop |
| Rock | Classic Rock, Punk, Grunge, Emo, Indie Rock |
| Metal | Heavy Metal, Thrash Metal, Nu Metal, Glam Metal, Metalcore |
| Rap | Trap, Conscious Hip Hop, Golden Age Hip Hop, Alternative Hip Hop, Pop Rap |
| R&B | Contemporary R&B, Alternative R&B, Neo Soul, Classic Soul, 90s R&B |
| Country | Classic Country, Contemporary Country, Country Pop, Outlaw & Americana, Bluegrass |
| Electronic | French House, Trip Hop, Ambient & IDM, Synthwave, UK Garage |
| EDM | Big Room House, Dubstep, Melodic Bass, Tech House, Trance |
| Jazz | Bebop, Cool Jazz, Swing & Big Band, Jazz Fusion, Vocal Jazz |

- Each answer comes back with a probability for every option. The vibe screen shows the top genre and sub-genre with their confidence and, under "Full breakdown", a ranked bar for each genre and for each sub-genre of the top one; each snapshot in the gallery is labelled with its genre and sub-genre too (hover for the full breakdown).
- If Spotify is connected, song cards picked to match the newest result's sub-genre probabilities follow, with a button to save them as a playlist (see [Spotify](#spotify)).
- If several snapshots are in flight, only the newest result is shown.

### Spotting a person

- `detector.worker.js` loads OpenCV.js and `models/MobileNetSSD_deploy.*` (a Caffe SSD trained on PASCAL VOC) in a Web Worker, so the ~0.5–1 s inference doesn't freeze the page.
- Each frame is resized to 300×300 and run through the network; only "person" detections above the confidence threshold (the Sensitivity slider) and covering at least 4% of the frame are kept. That excludes people far away in the background.
- Because it detects whole people, not faces, it still works if you're facing away, looking down, or only partly in frame.
- Presence is debounced: 3 consecutive detections → **present**; nobody detected for the "Away after" grace period → **away**.
- When someone arrives, a 3-second countdown appears over the video, then a full-resolution snapshot (mirrored like the preview, without detection boxes) is added to the Snapshots gallery; click one to download it. Leaving before the countdown ends cancels it, and only one snapshot is taken per arrival.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
