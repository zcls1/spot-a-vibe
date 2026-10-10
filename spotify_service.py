# Import random to pick a different set of songs each time
import random

# Import re to tidy up song titles when looking for repeats
import re

# Import requests to communicate with Spotify
import requests

# Import the function that loads credentials from .env
from dotenv import load_dotenv

# Import the well-known artists to pick songs from, grouped by sub-genre
from subgenre_artists import SUBGENRE_ARTISTS

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

# How many artists each playlist draws from, and how many songs each one contributes
ARTISTS_PER_PLAYLIST = 5
SONGS_PER_ARTIST = 2

# Songs are picked at random from each artist's top few search results, which are
# usually their biggest songs, so picking the same artist twice gives some variety
TOP_SONGS_PER_ARTIST = 5

# How strongly to favour the sub-genres Clef rates highest. 1 picks artists in direct
# proportion to their sub-genre's probability; higher values lean harder towards the
# top sub-genre. Each sub-genre only has 5 artists, so leaning too hard would give the
# same 5 artists on every scan.
SHARPNESS = 1

# How many of the top genre search results to fill from if the artist searches come
# up short. Deeper results are less popular, so this keeps the songs recognisable.
POOL_SIZE = 50

# The most tracks Spotify returns per search, so the pool is fetched in pages of this size
PAGE_SIZE = 10


def search_songs(token, genre, subgenre_probabilities, limit=10):
    # Choose artists from the genre's sub-genres, favouring the ones Clef rated highest
    artists = pick_artists(genre, subgenre_probabilities, ARTISTS_PER_PLAYLIST)

    # Song titles already picked, so the same song never appears twice
    seen = set()
    tracks = []

    for name in artists:
        # Search for the artist's songs; Spotify ranks their best-known songs first
        results = _search_tracks(token, f'artist:"{name}"', PAGE_SIZE, 0)

        # Keep songs the artist actually performs on (search also finds covers and
        # tributes), once each, skipping songs already picked for another artist
        own = {}
        for track in results:
            if not any(artist["name"].casefold() == name.casefold() for artist in track["artists"]):
                continue
            title = _base_title(track["name"])
            if title not in seen:
                own.setdefault(title, track)

        # Pick a few of their top songs at random
        top = list(own.items())[:TOP_SONGS_PER_ARTIST]
        for title, track in random.sample(top, min(SONGS_PER_ARTIST, len(top))):
            seen.add(title)
            tracks.append(track)

    # If an artist search found too little, fill the rest from the genre's top songs
    if len(tracks) < limit:
        extra = [track for track in _genre_tracks(token, genre) if _base_title(track["name"]) not in seen]
        tracks.extend(random.sample(extra, min(limit - len(tracks), len(extra))))

    # Mix the artists together rather than listing each artist's songs side by side
    tracks = tracks[:limit]
    random.shuffle(tracks)

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


def pick_artists(genre, subgenre_probabilities, count):
    # Each artist is weighted by Clef's probability for their sub-genre.
    # Example: for Rap with Trap at 0.6 and Pop Rap at 0.2, each Trap artist is three
    # times as likely to be picked as each Pop Rap artist.
    scores = {}
    for subgenre, artists in SUBGENRE_ARTISTS[genre].items():
        for name in artists:
            scores[name] = max(scores.get(name, 0), subgenre_probabilities.get(subgenre, 0))

    # Draw artists at random, weighted by their score, without picking anyone twice.
    # Each artist gets a random key that tends to be larger the higher their weight;
    # the largest keys win.
    keys = {
        name: random.random() ** (1 / score ** SHARPNESS)
        for name, score in scores.items()
        if score > 0
    }
    return sorted(keys, key=keys.get, reverse=True)[:count]


def _genre_tracks(token, genre):
    # Search by genre rather than plain text, so "Jazz" finds jazz songs instead of
    # songs with "jazz" in the title. Spotify's genre names are lowercase.
    # Example: "R&B" becomes genre:"r&b"
    query = f'genre:"{genre.lower()}"'

    # Collect the top results for the genre, one page at a time
    pool = []
    for offset in range(0, POOL_SIZE, PAGE_SIZE):
        page = _search_tracks(token, query, PAGE_SIZE, offset)
        pool.extend(page)

        # A short page means there are no more results
        if len(page) < PAGE_SIZE:
            break

    # The same song often appears more than once (e.g. on a single and on an album),
    # so keep only the first, highest-ranked copy of each title
    unique = {}
    for track in pool:
        unique.setdefault(_base_title(track["name"]), track)
    return list(unique.values())


def _base_title(name):
    # The song's title without versions, so "Song - Remastered 2011" and
    # "Song (feat. Someone)" count as the same song as "Song"
    return re.split(r" - | \(", name)[0].strip().casefold()


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


def create_playlist(token, name, uris):
    # Include the signed-in user's access token in every request
    headers = {"Authorization": f"Bearer {token}"}

    # Create an empty private playlist on the user's account
    response = requests.post(
        CREATE_PLAYLIST_URL,
        headers=headers,
        json={
            "name": f"spot-a-vibe: {name}",
            "description": f"{name} songs picked by spot-a-vibe from your style.",
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
