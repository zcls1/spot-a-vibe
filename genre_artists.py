# Well-known artists to build playlists from, each with how much of their sound belongs
# to each genre. Spotify no longer tells apps how popular a song is, so this list is
# what keeps the songs recognisable.
#
# Weights for an artist add up to 1. A pure rap artist is {"Rap": 1}; Drake, who
# crosses into R&B and pop, is {"Rap": 0.6, "R&B": 0.3, "Pop": 0.1}. spotify_service
# matches these against Clef's probabilities: the more an artist's genres line up with
# the vibe, the more likely they are to be picked.
#
# To add an artist, use their name exactly as Spotify spells it.

# Import the genre names Clef chooses from, to check the weights below
from endpoint.handler import GENRES

ARTISTS = {
    # --- Pop ---
    "Taylor Swift": {"Pop": 0.85, "Country": 0.15},
    "Ariana Grande": {"Pop": 0.7, "R&B": 0.3},
    "Billie Eilish": {"Pop": 0.8, "Electronic": 0.2},
    "Dua Lipa": {"Pop": 0.8, "EDM": 0.2},
    "Harry Styles": {"Pop": 0.8, "Rock": 0.2},
    "Olivia Rodrigo": {"Pop": 0.7, "Rock": 0.3},
    "Ed Sheeran": {"Pop": 1},
    "Sabrina Carpenter": {"Pop": 1},
    "Bruno Mars": {"Pop": 0.6, "R&B": 0.4},
    "Lady Gaga": {"Pop": 0.8, "EDM": 0.2},
    "Katy Perry": {"Pop": 1},
    "Chappell Roan": {"Pop": 1},
    "The Weeknd": {"Pop": 0.5, "R&B": 0.5},
    "Justin Bieber": {"Pop": 0.7, "R&B": 0.3},

    # --- Rock ---
    "Queen": {"Rock": 1},
    "Foo Fighters": {"Rock": 0.9, "Metal": 0.1},
    "Arctic Monkeys": {"Rock": 1},
    "Nirvana": {"Rock": 0.9, "Metal": 0.1},
    "Red Hot Chili Peppers": {"Rock": 1},
    "The Rolling Stones": {"Rock": 1},
    "Fleetwood Mac": {"Rock": 0.8, "Pop": 0.2},
    "Imagine Dragons": {"Rock": 0.6, "Pop": 0.4},
    "Linkin Park": {"Rock": 0.6, "Metal": 0.3, "Rap": 0.1},
    "Green Day": {"Rock": 1},
    "The Killers": {"Rock": 0.8, "Pop": 0.2},
    "AC/DC": {"Rock": 0.7, "Metal": 0.3},
    "Guns N' Roses": {"Rock": 0.7, "Metal": 0.3},
    "Paramore": {"Rock": 0.7, "Pop": 0.3},

    # --- Metal ---
    "Metallica": {"Metal": 1},
    "Iron Maiden": {"Metal": 1},
    "Slipknot": {"Metal": 1},
    "System Of A Down": {"Metal": 0.9, "Rock": 0.1},
    "Black Sabbath": {"Metal": 0.8, "Rock": 0.2},
    "Avenged Sevenfold": {"Metal": 0.8, "Rock": 0.2},
    "Megadeth": {"Metal": 1},
    "Pantera": {"Metal": 1},
    "Bring Me The Horizon": {"Metal": 0.7, "Rock": 0.2, "Electronic": 0.1},
    "Ghost": {"Metal": 0.7, "Rock": 0.3},
    "Gojira": {"Metal": 1},
    "Korn": {"Metal": 0.8, "Rap": 0.2},
    "Rage Against The Machine": {"Metal": 0.5, "Rock": 0.3, "Rap": 0.2},
    "Judas Priest": {"Metal": 1},

    # --- Rap ---
    "Kendrick Lamar": {"Rap": 1},
    "Drake": {"Rap": 0.6, "R&B": 0.3, "Pop": 0.1},
    "Eminem": {"Rap": 1},
    "Travis Scott": {"Rap": 0.9, "Electronic": 0.1},
    "J. Cole": {"Rap": 1},
    "Kanye West": {"Rap": 0.9, "Electronic": 0.1},
    "Nicki Minaj": {"Rap": 0.7, "Pop": 0.3},
    "Lil Wayne": {"Rap": 1},
    "Tyler, The Creator": {"Rap": 0.7, "R&B": 0.3},
    "Future": {"Rap": 1},
    "21 Savage": {"Rap": 1},
    "Doja Cat": {"Rap": 0.4, "Pop": 0.4, "R&B": 0.2},
    "Post Malone": {"Rap": 0.4, "Pop": 0.4, "Country": 0.2},
    "Megan Thee Stallion": {"Rap": 1},
    "Cardi B": {"Rap": 0.9, "Pop": 0.1},
    "JAY-Z": {"Rap": 1},
    "Kid Cudi": {"Rap": 0.8, "Electronic": 0.2},

    # --- R&B ---
    "SZA": {"R&B": 0.8, "Pop": 0.2},
    "Frank Ocean": {"R&B": 1},
    "Beyoncé": {"R&B": 0.6, "Pop": 0.4},
    "Usher": {"R&B": 0.8, "Pop": 0.2},
    "Alicia Keys": {"R&B": 1},
    "Daniel Caesar": {"R&B": 1},
    "H.E.R.": {"R&B": 1},
    "Summer Walker": {"R&B": 1},
    "Brent Faiyaz": {"R&B": 1},
    "Chris Brown": {"R&B": 0.7, "Pop": 0.2, "Rap": 0.1},
    "Rihanna": {"R&B": 0.5, "Pop": 0.5},
    "Steve Lacy": {"R&B": 0.8, "Rock": 0.2},
    "Miguel": {"R&B": 1},
    "Jhené Aiko": {"R&B": 1},

    # --- Country ---
    "Morgan Wallen": {"Country": 0.9, "Rock": 0.1},
    "Luke Combs": {"Country": 1},
    "Zach Bryan": {"Country": 1},
    "Chris Stapleton": {"Country": 0.8, "Rock": 0.2},
    "Kacey Musgraves": {"Country": 0.8, "Pop": 0.2},
    "Dolly Parton": {"Country": 1},
    "Johnny Cash": {"Country": 1},
    "Lainey Wilson": {"Country": 1},
    "Jason Aldean": {"Country": 0.8, "Rock": 0.2},
    "Carrie Underwood": {"Country": 1},
    "Kenny Chesney": {"Country": 1},
    "Shaboozey": {"Country": 0.7, "Rap": 0.3},
    "Luke Bryan": {"Country": 1},
    "Willie Nelson": {"Country": 1},

    # --- Electronic ---
    "Daft Punk": {"Electronic": 0.8, "EDM": 0.2},
    "Aphex Twin": {"Electronic": 1},
    "The Chemical Brothers": {"Electronic": 0.7, "EDM": 0.3},
    "Gorillaz": {"Electronic": 0.5, "Rock": 0.3, "Rap": 0.2},
    "Fred again..": {"Electronic": 0.6, "EDM": 0.4},
    "Kraftwerk": {"Electronic": 1},
    "Justice": {"Electronic": 0.7, "EDM": 0.3},
    "Massive Attack": {"Electronic": 1},
    "Moby": {"Electronic": 1},
    "Bonobo": {"Electronic": 1},
    "Jamie xx": {"Electronic": 0.8, "EDM": 0.2},
    "Röyksopp": {"Electronic": 1},
    "Disclosure": {"Electronic": 0.5, "EDM": 0.3, "R&B": 0.2},
    "Four Tet": {"Electronic": 1},

    # --- EDM ---
    "Calvin Harris": {"EDM": 0.7, "Pop": 0.3},
    "David Guetta": {"EDM": 0.7, "Pop": 0.3},
    "Avicii": {"EDM": 0.9, "Pop": 0.1},
    "Martin Garrix": {"EDM": 1},
    "Marshmello": {"EDM": 0.7, "Pop": 0.3},
    "Swedish House Mafia": {"EDM": 1},
    "Tiësto": {"EDM": 1},
    "Skrillex": {"EDM": 0.8, "Electronic": 0.2},
    "Zedd": {"EDM": 0.7, "Pop": 0.3},
    "The Chainsmokers": {"EDM": 0.5, "Pop": 0.5},
    "Kygo": {"EDM": 0.7, "Pop": 0.3},
    "Alesso": {"EDM": 1},
    "deadmau5": {"EDM": 0.6, "Electronic": 0.4},
    "ILLENIUM": {"EDM": 1},
    "John Summit": {"EDM": 1},

    # --- Jazz ---
    "Miles Davis": {"Jazz": 1},
    "John Coltrane": {"Jazz": 1},
    "Louis Armstrong": {"Jazz": 1},
    "Ella Fitzgerald": {"Jazz": 1},
    "Billie Holiday": {"Jazz": 1},
    "Duke Ellington": {"Jazz": 1},
    "Dave Brubeck": {"Jazz": 1},
    "Nina Simone": {"Jazz": 0.7, "R&B": 0.3},
    "Chet Baker": {"Jazz": 1},
    "Herbie Hancock": {"Jazz": 0.8, "Electronic": 0.1, "R&B": 0.1},
    "Norah Jones": {"Jazz": 0.7, "Pop": 0.3},
    "Frank Sinatra": {"Jazz": 0.7, "Pop": 0.3},
    "Kamasi Washington": {"Jazz": 1},
    "Thelonious Monk": {"Jazz": 1},
    "Robert Glasper": {"Jazz": 0.6, "R&B": 0.4},
}

# Catch typos when the list is edited: every genre must be one Clef knows, and each
# artist's weights must add up to 1
for _artist, _weights in ARTISTS.items():
    assert set(_weights) <= set(GENRES), f"{_artist}: unknown genre in {_weights}"
    assert abs(sum(_weights.values()) - 1) < 1e-6, f"{_artist}: weights add up to {sum(_weights.values())}"
