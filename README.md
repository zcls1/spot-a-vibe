# spot-a-vibe
Knight Hacks IX

Detects whether a person is in front of your laptop camera, entirely in the browser, using [OpenCV.js](https://docs.opencv.org/4.9.0/opencv.js) and a MobileNet-SSD object detector.

## Run

The Flask server serves the page and runs genre detection with [Clef-Flash](https://huggingface.co/Cloudflare/clef-flash). The model is ~19 GB (9.4B parameters, bf16) and its model card was tested on an NVIDIA H200, so run the server on a machine with a large GPU:

```sh
pip install -r requirements.txt
python server.py            # downloads the model on first run, then serves http://127.0.0.1:8000
```

To work on the front end without a GPU, `CLEF_STUB=1 python server.py` skips the model and returns random genre probabilities.

Camera access requires a secure context, so open the page via `localhost` or HTTPS, not `file://`.

## How it works

- `detector.worker.js` loads OpenCV.js and `models/MobileNetSSD_deploy.*` (a Caffe SSD trained on PASCAL VOC) in a Web Worker, so the ~0.5–1 s inference doesn't freeze the page.
- Each frame is resized to 300×300 and run through the network; only "person" detections above the confidence threshold (the Sensitivity slider) and covering at least 4% of the frame are kept. That excludes people far away in the background.
- Because it detects whole people, not faces, it still works if you're facing away, looking down, or only partly in frame.
- Presence is debounced: 3 consecutive detections → **present**; nobody detected for the "Away after" grace period → **away**.
- When someone arrives, a 3-second countdown appears over the video, then a full-resolution snapshot (mirrored like the preview, without detection boxes) is added to the Snapshots gallery; click one to download it. Leaving before the countdown ends cancels it, and only one snapshot is taken per arrival.
- Each snapshot is uploaded to `POST /api/genre`. The server opens it with Pillow and sends it to Clef-Flash as a Jev/SystemOne `choice` question over 9 genres. The predicted genre and confidence appear under the snapshot; hover for the full breakdown.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
