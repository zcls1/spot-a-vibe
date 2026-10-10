# Import tools for reading credentials and sending API requests
import os
import requests
import json
from dotenv import load_dotenv

# Load credentials from the .env file
load_dotenv()

# Get Cloudflare credentials from environment variables
ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

# Build the Cloudflare Workers AI URL
MODEL_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/"
    f"{ACCOUNT_ID}/ai/run/@cf/meta/llama-3.1-8b-instruct"
)


def get_music_tags(vibe):
    # Make sure Cloudflare credentials are available
    if not ACCOUNT_ID or not API_TOKEN:
        raise RuntimeError("Cloudflare credentials are missing.")

    # Ask AI to generate music tags for the detected vibe
    response = requests.post(
        MODEL_URL,
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You recommend music based on a person's vibe. "
                        "Return only valid JSON with a music_tags array "
                        "containing 3 to 5 short mood or genre tags."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Suggest music tags for this vibe: {vibe}",
                },
            ],
            "max_tokens": 100,
        },
        timeout=30,
    )

    # Raise an error if Cloudflare rejects the request
    response.raise_for_status()

    # Get the result returned by Cloudflare
    result = response.json()["result"]

    # Try to read tags from the parsed response
    tags = result.get("response", {}).get("music_tags")

    # If needed, parse the AI's JSON text
    if not tags:
        content = result["choices"][0]["message"]["content"]
        tags = json.loads(content).get("music_tags")

    # Make sure the AI returned a list of tags
    if not isinstance(tags, list) or not tags:
        raise ValueError("AI did not return valid music tags.")

    # Return the tags so Spotify can search for songs
    return tags
