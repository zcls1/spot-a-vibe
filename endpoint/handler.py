"""Clef-Flash genre detection for spot-a-vibe.

Each image gets two passes: first the genre, then the sub-genre within that genre
(SUBGENRES), so the second question only offers styles of the genre already chosen.

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

# Five sub-genres per genre, each with a short description so the model knows what the
# style sounds and looks like. Asked in a second pass, over the top genre's sub-genres
# only. Picked to differ in look as well as sound, since the model only sees the image.
SUBGENRES = {
    "Pop": {
        "Dance Pop": "upbeat, glossy club-ready pop",
        "Alt Pop": "moody, offbeat, left-of-centre pop",
        "Singer-Songwriter Pop": "heartfelt, lyric-driven pop",
        "K-Pop": "polished, highly styled Korean pop",
        "Synth-pop": "retro, synthesizer-driven pop with an '80s feel",
    },
    "Rock": {
        "Classic Rock": "'60s and '70s guitar rock",
        "Punk": "fast, loud, rebellious, DIY rock",
        "Grunge": "heavy, sludgy '90s Seattle rock",
        "Emo": "emotional, dramatic 2000s pop-punk and emo",
        "Indie Rock": "jangly, guitar-led independent rock",
    },
    "Metal": {
        "Heavy Metal": "classic '70s and '80s metal with soaring vocals",
        "Thrash Metal": "fast, aggressive, riff-heavy metal",
        "Nu Metal": "late-'90s metal mixed with hip hop",
        "Glam Metal": "flamboyant, big-haired '80s arena metal",
        "Metalcore": "modern metal with breakdowns and screamed vocals",
    },
    "Rap": {
        "Trap": "modern, bass-heavy Southern rap",
        "Conscious Hip Hop": "lyrical, socially aware rap",
        "Golden Age Hip Hop": "'90s boom-bap rap",
        "Alternative Hip Hop": "experimental, genre-bending rap",
        "Pop Rap": "melodic, chart-topping rap",
    },
    "R&B": {
        "Contemporary R&B": "smooth, modern R&B",
        "Alternative R&B": "atmospheric, experimental R&B",
        "Neo Soul": "warm, organic, jazz-tinged soul",
        "Classic Soul": "'60s and '70s soul and Motown",
        "90s R&B": "'90s and early-2000s R&B and girl/boy groups",
    },
    "Country": {
        "Classic Country": "traditional country from the '50s to the '70s",
        "Contemporary Country": "modern mainstream country",
        "Country Pop": "polished, pop-leaning country",
        "Outlaw & Americana": "gritty, rootsy, outlaw-style country",
        "Bluegrass": "acoustic, string-band country with banjo and fiddle",
    },
    "Electronic": {
        "French House": "filtered, funky, disco-sampling house",
        "Trip Hop": "slow, dark, atmospheric downtempo",
        "Ambient & IDM": "textural, cerebral electronic listening music",
        "Synthwave": "neon, retro-futuristic '80s-inspired electronic",
        "UK Garage": "skippy, shuffling UK club music",
    },
    "EDM": {
        "Big Room House": "huge festival main-stage house drops",
        "Dubstep": "aggressive, wobbling bass music",
        "Melodic Bass": "emotional, euphoric future bass",
        "Tech House": "groovy, minimal club house",
        "Trance": "soaring, hypnotic, uplifting dance music",
    },
    "Jazz": {
        "Bebop": "fast, virtuosic '40s small-group jazz",
        "Cool Jazz": "relaxed, understated '50s jazz",
        "Swing & Big Band": "'30s and '40s dance-band jazz",
        "Jazz Fusion": "electric jazz mixed with rock and funk",
        "Vocal Jazz": "jazz standards led by a singer",
    },
}


def subgenre_question(genre):
    """The second-pass question: which of the genre's sub-genres fits the person best."""
    return {
        "type": "choice",
        "instructions": (
            f"This person's aesthetic suggests they prefer {genre} music. Determine which style "
            f"of {genre} best fits their general aesthetic (clothes, accessories). Do not take "
            "characteristics like height, race or weight into consideration."
        ),
        "criteria": {
            name: f"The person's aesthetic suggests they prefer {name} ({description})."
            for name, description in SUBGENRES[genre].items()
        },
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
        """Asks for the genre, then for the sub-genre within it. The response is the first
        pass's, with the second pass's answer added under answers["subgenre"]."""
        with self.lock:
            result = self.ask(image, "genre", GENRE_QUESTION)
            genre = result["answers"]["genre"]["choice"]
            second = self.ask(image, "subgenre", subgenre_question(genre))
        result["answers"]["subgenre"] = second["answers"]["subgenre"]
        # Report the tokens used by both passes.
        usage = result.setdefault("usage", {})
        for key, value in second.get("usage", {}).items():
            usage[key] = usage.get(key, 0) + value
        return result

    def ask(self, image, name, question):
        body = {
            "model": MODEL_ID,
            "state": {"task": "Review the given image"},
            "images": [image],
            "questions": {name: question},
        }
        return self.systemone(self.model, self.processor, body)

    def __call__(self, data):
        # The endpoint decodes image request bodies into an RGB PIL image under "inputs".
        return self.classify(data["inputs"])
