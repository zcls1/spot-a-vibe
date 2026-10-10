# Import Flask tools for creating API endpoints and returning JSON
from flask import Flask, jsonify, request

# Import the Spotify search function
from spotify_service import search_songs

# Import the AI function that generates music tags
from clef_service import get_music_tags

# Create the Flask application
app = Flask(__name__)


# Existing endpoint: search Spotify using tags provided by the user
@app.route("/api/songs", methods=["POST"])
def get_songs():
    # Read the JSON data sent to the API
    data = request.get_json(silent=True) or {}

    # Get the music tags from the request
    tags = data.get("tags", [])

    # Make sure the tags are a non-empty list
    if not isinstance(tags, list) or not tags:
        return jsonify({"error": "Please provide a list of music tags."}), 400

    try:
        # Search Spotify for matching songs
        songs = search_songs(tags)

        # Return the tags and matching songs
        return jsonify({"tags": tags, "songs": songs})

    except Exception:
        # Log the error for debugging
        app.logger.exception("Spotify search failed")

        # Send a safe error message to the client
        return jsonify({"error": "Spotify search failed. Check the server logs."}), 502


# New endpoint: use AI to turn a detected vibe into Spotify recommendations
@app.route("/api/recommend", methods=["POST"])
def recommend_songs():
    # Read the JSON data sent to the API
    data = request.get_json(silent=True) or {}

    # Get the detected vibe from the request
    vibe = data.get("vibe", "")

    # Make sure a vibe was provided as text
    if not isinstance(vibe, str) or not vibe.strip():
        return jsonify({"error": "Please provide a vibe as text."}), 400

    try:
        # Ask Cloudflare AI to generate music tags
        tags = get_music_tags(vibe.strip())

        # Search Spotify using the AI-generated tags
        songs = search_songs(tags)

        # Return the vibe, tags, and recommended songs
        return jsonify({
            "vibe": vibe,
            "tags": tags,
            "songs": songs
        })

    except Exception:
        # Log the error so we can diagnose it
        app.logger.exception("AI recommendation failed")

        # Return a safe error message
        return jsonify({
            "error": "AI recommendation failed. Check the server logs."
        }), 502


# Start the development server when this file is run directly
if __name__ == "__main__":
    app.run(debug=True)