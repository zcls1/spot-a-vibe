# spot-a-vibe
Knight Hacks IX

Step in front of your laptop camera and spot-a-vibe guesses your music taste. When it sees someone, it counts down, snaps a photo, and asks [Cloudflare's Clef-Flash](https://huggingface.co/Cloudflare/clef-flash) model which genre fits their style. The result appears under the camera feed as a "Detected vibe": the top genre, how confident the model is, and a ranked breakdown across all nine genres: Pop, Rock, Metal, Rap, R&B, Country, Electronic, EDM and Jazz.

Person detection runs entirely in the browser with [OpenCV.js](https://docs.opencv.org/4.9.0/opencv.js) and a MobileNet-SSD object detector. Only the snapshots are sent to the local Flask server for genre detection.

## Run

The Flask server serves the page and runs genre detection with [Clef-Flash](https://huggingface.co/Cloudflare/clef-flash), loaded directly with PyTorch. The model is ~19 GB (9.4B parameters, bf16), so you need a machine with an NVIDIA GPU or an Apple Silicon Mac with enough memory (tested on an M3 Max with 36 GB).

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py            # serves http://127.0.0.1:8000
```

The first run downloads the model (~19 GB). Startup then takes about a minute: loading the weights, plus one warm-up pass so the first snapshot isn't slow. On an M3 Max each snapshot takes about 2 seconds after that. The device is picked automatically (CUDA, then Apple GPU, then CPU); override it with `CLEF_DEVICE`.

To work on the front end without the model, `CLEF_STUB=1 python server.py` skips it and returns random genre probabilities.

Camera access requires a secure context, so open the page via `localhost` or HTTPS, not `file://`.

## How it works

### Genre detection

- Each snapshot is uploaded to `POST /api/genre`. The server opens it with Pillow and sends it to Clef-Flash as a Jev/SystemOne `choice` question over the 9 genres, asking it to judge only clothing and accessories.
- The answer comes back with a probability for every genre. The "Detected vibe" card under the camera shows the top genre, its confidence and a ranked bar for each genre; each snapshot in the gallery is labelled with its genre too (hover for the full breakdown).
- The card shows the current stage: waiting, countdown, "Reading the vibe…" while the model runs, then the result, or the error if the model fails. If several snapshots are in flight, only the newest result is shown.

### Spotting a person

- `detector.worker.js` loads OpenCV.js and `models/MobileNetSSD_deploy.*` (a Caffe SSD trained on PASCAL VOC) in a Web Worker, so the ~0.5–1 s inference doesn't freeze the page.
- Each frame is resized to 300×300 and run through the network; only "person" detections above the confidence threshold (the Sensitivity slider) and covering at least 4% of the frame are kept. That excludes people far away in the background.
- Because it detects whole people, not faces, it still works if you're facing away, looking down, or only partly in frame.
- Presence is debounced: 3 consecutive detections → **present**; nobody detected for the "Away after" grace period → **away**.
- When someone arrives, a 3-second countdown appears over the video, then a full-resolution snapshot (mirrored like the preview, without detection boxes) is added to the Snapshots gallery; click one to download it. Leaving before the countdown ends cancels it, and only one snapshot is taken per arrival.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
