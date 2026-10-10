# spot-a-vibe
Knight Hacks IX

Detects whether someone is in front of your laptop camera, entirely in the browser, using [OpenCV.js](https://docs.opencv.org/4.9.0/opencv.js) Haar cascades.

## Run

Camera access requires a secure context, so serve the folder over `localhost` (opening `index.html` as a `file://` won't work):

```sh
python3 -m http.server 8000
# then open http://localhost:8000
```

## How it works

- Frames are downscaled to 320px wide, converted to grayscale and histogram-equalised.
- `models/haarcascade_frontalface_default.xml` finds faces looking at the screen; if none are found, `haarcascade_profileface.xml` runs on the frame and its mirror to catch people turned sideways.
- Presence is debounced: 3 consecutive detections → **present**; no face for the "Away after" grace period → **away**.
- Arrivals/departures are logged, reflected in the tab title, and optionally sent as desktop notifications.
