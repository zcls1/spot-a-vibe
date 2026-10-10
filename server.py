"""Flask server for spot-a-vibe.

Serves the static app and exposes POST /api/genre, which runs a snapshot through
Cloudflare's Clef-Flash decision model and returns a Jev/SystemOne response body.

Environment variables:
  CLEF_MODEL   Hugging Face repo or local path (default: Cloudflare/clef-flash)
  CLEF_DEVICE  cuda, mps or cpu (default: the first one available)
  CLEF_STUB    set to 1 to skip loading the model and return random probabilities,
               for working on the front end without a GPU
"""

import os
import random
import sys
import threading

from flask import Flask, jsonify, request, send_from_directory
from PIL import Image, UnidentifiedImageError

MODEL_ID = os.environ.get("CLEF_MODEL", "Cloudflare/clef-flash")
STUB = os.environ.get("CLEF_STUB") == "1"

GENRES = ["Pop", "Rock", "Metal", "Rap", "R&B", "Country", "Electronic", "EDM", "Jazz"]

GENRE_QUESTION = {
    "type": "choice",
    "instructions": (
        "Determine the preferred genre of the person in this image based off of their general "
        "aesthetic (clothes, accessories). Do not take characteristics like height, race or "
        "weight into consideration."
    ),
    # A choice question maps each option ID to a description of that option.
    "criteria": {genre: f"The person's aesthetic suggests they prefer {genre} music." for genre in GENRES},
}

app = Flask(__name__, static_folder=None)
ROOT = os.path.dirname(os.path.abspath(__file__))

model = processor = systemone = None
# The model runs on a single device; serialise requests so they don't contend for it.
inference_lock = threading.Lock()


def pick_device():
    import torch

    if os.environ.get("CLEF_DEVICE"):
        return os.environ["CLEF_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model():
    global model, processor, systemone
    from huggingface_hub import snapshot_download

    path = snapshot_download(MODEL_ID)
    # joint_schema_model.py ships inside the model repo rather than as a package.
    sys.path.insert(0, path)
    from joint_schema_model import load_release_model
    from joint_schema_model import systemone as _systemone

    device = pick_device()
    print(f"Loading {MODEL_ID} on {device}…", flush=True)
    model, processor = load_release_model(path, device=device)
    systemone = _systemone

    # The first forward pass is much slower (on an M3 Max, ~28 s vs ~2 s after) while
    # the GPU compiles kernels. Do it now so the first real snapshot isn't stuck.
    print("Warming up the model…", flush=True)
    classify(Image.new("RGB", (640, 480), "gray"))
    print("Model ready.", flush=True)


def classify(image):
    body = {
        "model": MODEL_ID,
        "state": {"task": "Review the given image"},
        "images": [image],
        "questions": {"genre": GENRE_QUESTION},
    }
    if STUB:
        weights = {genre: random.random() ** 3 for genre in GENRES}
        total = sum(weights.values())
        probabilities = {genre: round(w / total, 4) for genre, w in weights.items()}
        choice = max(probabilities, key=probabilities.get)
        return {
            "model": "stub",
            "answers": {"genre": {
                "type": "choice",
                "choice": choice,
                "confidence": probabilities[choice],
                "probabilities": probabilities,
            }},
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
    with inference_lock:
        return systemone(model, processor, body)


@app.post("/api/genre")
def genre():
    upload = request.files.get("image")
    if upload is None:
        return jsonify(error="expected an image file in the 'image' form field"), 400
    try:
        # Decode the uploaded snapshot with Pillow. convert() forces the full decode
        # while the upload stream is still open and drops any alpha channel.
        image = Image.open(upload.stream).convert("RGB")
    except UnidentifiedImageError:
        return jsonify(error="could not read the uploaded image"), 400
    try:
        return jsonify(classify(image))
    except Exception as err:
        # Surface model failures (e.g. an unsupported op on the chosen device) to the page.
        app.logger.exception("genre classification failed")
        return jsonify(error=f"model error: {err}"), 500


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


if not STUB:
    load_model()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=False)
