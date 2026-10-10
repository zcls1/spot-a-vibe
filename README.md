# spot-a-vibe
Knight Hacks IX

Detects whether a person is in front of your laptop camera, entirely in the browser, using [OpenCV.js](https://docs.opencv.org/4.9.0/opencv.js) and a MobileNet-SSD object detector.

## Run

Camera access requires a secure context, so serve the folder over `localhost` (opening `index.html` as a `file://` won't work):

```sh
python3 -m http.server 8000
# then open http://localhost:8000
```

## How it works

- `detector.worker.js` loads OpenCV.js and `models/MobileNetSSD_deploy.*` (a Caffe SSD trained on PASCAL VOC) in a Web Worker, so the ~0.5–1 s inference doesn't freeze the page.
- Each frame is resized to 300×300 and run through the network; only "person" detections above the confidence threshold (the Sensitivity slider) and covering at least 4% of the frame are kept. That excludes people far away in the background.
- Because it detects whole people, not faces, it still works if you're facing away, looking down, or only partly in frame.
- Presence is debounced: 3 consecutive detections → **present**; nobody detected for the "Away after" grace period → **away**.
- When someone arrives, a 3-second countdown appears over the video, then a full-resolution snapshot (mirrored like the preview, without detection boxes) is added to the Snapshots gallery; click one to download it. Leaving before the countdown ends cancels it, and only one snapshot is taken per arrival.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
