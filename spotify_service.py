# Import random to pick a different set of songs each time
import random

# Import requests to communicate with Spotify
import requests

# Import the function that loads credentials from .env
from dotenv import load_dotenv

# Load the private Spotify credentials from the .env file
load_dotenv()

# Spotify's URL for requesting an access token (used by the sign-in flow in server.py)
TOKEN_URL = "https://accounts.spotify.com/api/token"

# Spotify's URL for searching songs
SEARCH_URL = "https://api.spotify.com/v1/search"

# Spotify's URL for creating a playlist on the signed-in user's account
CREATE_PLAYLIST_URL = "https://api.spotify.com/v1/me/playlists"

# Spotify's URL for adding songs to a playlist
PLAYLIST_ITEMS_URL = "https://api.spotify.com/v1/playlists/{playlist_id}/items"

# How far into the search results the random starting point can be. Deeper results are
# less popular, so this keeps the songs recognisable while still varying them.
MAX_RANDOM_OFFSET = 100


def search_songs(token, genre, limit=10):
    # Search by genre rather than plain text, so "Jazz" finds jazz songs instead of
    # songs with "jazz" in the title. Spotify's genre names are lowercase.
    # Example: "R&B" becomes genre:"r&b"
    query = f'genre:"{genre.lower()}"'

    # Start at a random point in the results so the same genre gives different songs
    tracks = _search_tracks(token, query, limit, random.randint(0, MAX_RANDOM_OFFSET))

    # A genre with fewer results than the starting point returns nothing; start from the top
    if not tracks:
        tracks = _search_tracks(token, query, limit, 0)

    # Build a simpler list containing only the information we need
    return [
        {
            # Get the song's title
            "title": track["name"],

            # Combine all artist names into one string
            "artist": ", ".join(
                artist["name"] for artist in track["artists"]
            ),

            # Get the album cover if one is available
            "album_art": (
                track["album"]["images"][0]["url"]
                if track["album"]["images"]
                else None
            ),

            # Get the link to the song on Spotify
            "spotify_url": track["external_urls"].get("spotify"),

            # Get the Spotify track ID
            "track_id": track["id"],

            # Get the Spotify URI, which is how songs are added to a playlist
            "uri": track["uri"],
        }

        # Repeat these steps for every matching song
        for track in tracks
    ]


def _search_tracks(token, query, limit, offset):
    # Send a song-search request to Spotify
    response = requests.get(
        SEARCH_URL,

        # Include the signed-in user's access token to authorize the request
        headers={"Authorization": f"Bearer {token}"},

        # Tell Spotify what to search for and how many results to return (at most 10)
        params={
            "q": query,
            "type": "track",
            "limit": limit,
            "offset": offset,
        },

        # Stop waiting if Spotify takes too long
        timeout=15,
    )

    # Raise an error if the search request fails
    response.raise_for_status()

    # Return the list of matching tracks from the response
    return response.json()["tracks"]["items"]


def create_playlist(token, genre, uris):
    # Include the signed-in user's access token in every request
    headers = {"Authorization": f"Bearer {token}"}

    # Create an empty private playlist on the user's account
    response = requests.post(
        CREATE_PLAYLIST_URL,
        headers=headers,
        json={
            "name": f"spot-a-vibe: {genre}",
            "description": f"{genre} songs picked by spot-a-vibe from your style.",
            "public": False,
        },
        timeout=15,
    )

    # Raise an error if Spotify rejects the request
    response.raise_for_status()

    # Keep the new playlist's details
    playlist = response.json()

    # Add the songs to the playlist (Spotify allows up to 100 per request)
    response = requests.post(
        PLAYLIST_ITEMS_URL.format(playlist_id=playlist["id"]),
        headers=headers,
        json={"uris": uris},
        timeout=15,
    )

    # Raise an error if the songs couldn't be added
    response.raise_for_status()

    # Return what the page needs to show and open the playlist
    return {
        "id": playlist["id"],
        "name": playlist["name"],
        "spotify_url": playlist["external_urls"].get("spotify"),
    }
