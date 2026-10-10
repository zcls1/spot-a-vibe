"""Clef-Flash genre detection for spot-a-vibe.

Deployed as a Hugging Face Inference Endpoints custom handler: copy this file and
requirements.txt into the root of your duplicate of Cloudflare/clef-flash. The
endpoint then accepts an image body (Content-Type: image/png, image/jpeg, …) and
returns a Jev/SystemOne response body.

server.py also imports it to run the model locally, so this is the only copy of
the model code. Heavy imports stay inside the handler so the genre list can be
imported without torch installed.

Environment variables:
  CLEF_MODEL     Hugging Face repo, used when `path` doesn't contain the model
                 (default: Cloudflare/clef-flash)
  CLEF_REVISION  commit of CLEF_MODEL to download; pinned because the repo ships
                 code (joint_schema_model.py) that we import and run
  CLEF_DEVICE    cuda, mps or cpu (default: the first one available)
"""

import os
import sys
import threading

MODEL_ID = os.environ.get("CLEF_MODEL", "Cloudflare/clef-flash")
MODEL_REVISION = os.environ.get("CLEF_REVISION", "8b2e5fd17c09fd49bc2880b805d5323ec7ff4ff3")

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


def pick_device():
    import torch

    if os.environ.get("CLEF_DEVICE"):
        return os.environ["CLEF_DEVICE"]
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class EndpointHandler:
    def __init__(self, path=""):
        if not os.path.isfile(os.path.join(path, "joint_schema_model.py")):
            from huggingface_hub import snapshot_download

            path = snapshot_download(MODEL_ID, revision=MODEL_REVISION)
        # joint_schema_model.py ships inside the model repo rather than as a package.
        sys.path.insert(0, path)
        from joint_schema_model import load_release_model, systemone
        from PIL import Image

        device = pick_device()
        print(f"Loading {MODEL_ID} on {device}…", flush=True)
        self.model, self.processor = load_release_model(path, device=device)
        self.systemone = systemone
        # The model runs on a single device; serialise requests so they don't contend for it.
        self.lock = threading.Lock()

        # The first forward pass is much slower (on an M3 Max, ~28 s vs ~2 s after) while
        # the GPU compiles kernels. Do it now so the first real snapshot isn't stuck.
        print("Warming up the model…", flush=True)
        self.classify(Image.new("RGB", (640, 480), "gray"))
        print("Model ready.", flush=True)

    def classify(self, image):
        body = {
            "model": MODEL_ID,
            "state": {"task": "Review the given image"},
            "images": [image],
            "questions": {"genre": GENRE_QUESTION},
        }
        with self.lock:
            return self.systemone(self.model, self.processor, body)

    def __call__(self, data):
        # The endpoint decodes image request bodies into an RGB PIL image under "inputs".
        return self.classify(data["inputs"])
