# Well-known artists for each sub-genre in endpoint/handler.py's SUBGENRES. Spotify no
# longer tells apps how popular a song is, so this list is what keeps the songs
# recognisable. spotify_service picks artists from the top genre's sub-genres, favouring
# the sub-genres Clef thinks fit best.
#
# To add an artist, use their name exactly as Spotify spells it.

# Import the sub-genres Clef chooses from, to check the lists below match them
from endpoint.handler import SUBGENRES

SUBGENRE_ARTISTS = {
    "Pop": {
        "Dance Pop": ["Dua Lipa", "Lady Gaga", "Katy Perry", "Kylie Minogue", "Sabrina Carpenter"],
        "Alt Pop": ["Billie Eilish", "Lorde", "Lana Del Rey", "Chappell Roan", "Charli xcx"],
        "Singer-Songwriter Pop": ["Taylor Swift", "Ed Sheeran", "Olivia Rodrigo", "Adele", "Lewis Capaldi"],
        "K-Pop": ["BTS", "BLACKPINK", "NewJeans", "TWICE", "Stray Kids"],
        "Synth-pop": ["The Weeknd", "Depeche Mode", "a-ha", "Pet Shop Boys", "CHVRCHES"],
    },
    "Rock": {
        "Classic Rock": ["Led Zeppelin", "The Rolling Stones", "Queen", "Fleetwood Mac", "AC/DC"],
        "Punk": ["Ramones", "The Clash", "Sex Pistols", "Green Day", "blink-182"],
        "Grunge": ["Nirvana", "Pearl Jam", "Soundgarden", "Alice In Chains", "Stone Temple Pilots"],
        "Emo": ["My Chemical Romance", "Fall Out Boy", "Paramore", "Panic! At The Disco", "Dashboard Confessional"],
        "Indie Rock": ["Arctic Monkeys", "The Strokes", "The Killers", "Vampire Weekend", "Franz Ferdinand"],
    },
    "Metal": {
        "Heavy Metal": ["Iron Maiden", "Judas Priest", "Black Sabbath", "Motörhead", "Dio"],
        "Thrash Metal": ["Metallica", "Slayer", "Megadeth", "Anthrax", "Pantera"],
        "Nu Metal": ["Linkin Park", "Korn", "Slipknot", "Limp Bizkit", "System Of A Down"],
        "Glam Metal": ["Mötley Crüe", "Def Leppard", "Bon Jovi", "Poison", "Guns N' Roses"],
        "Metalcore": ["Bring Me The Horizon", "Killswitch Engage", "Bullet For My Valentine", "Architects", "Parkway Drive"],
    },
    "Rap": {
        "Trap": ["Future", "Travis Scott", "21 Savage", "Migos", "Young Thug"],
        "Conscious Hip Hop": ["Kendrick Lamar", "J. Cole", "Lupe Fiasco", "Common", "Talib Kweli"],
        "Golden Age Hip Hop": ["Nas", "The Notorious B.I.G.", "2Pac", "Wu-Tang Clan", "A Tribe Called Quest"],
        "Alternative Hip Hop": ["Tyler, The Creator", "Kanye West", "Kid Cudi", "Childish Gambino", "Outkast"],
        "Pop Rap": ["Drake", "Nicki Minaj", "Post Malone", "Doja Cat", "Jack Harlow"],
    },
    "R&B": {
        "Contemporary R&B": ["SZA", "Summer Walker", "Brent Faiyaz", "Jhené Aiko", "H.E.R."],
        "Alternative R&B": ["Frank Ocean", "Steve Lacy", "Daniel Caesar", "Solange", "The Weeknd"],
        "Neo Soul": ["Erykah Badu", "D'Angelo", "Jill Scott", "Lauryn Hill", "Maxwell"],
        "Classic Soul": ["Marvin Gaye", "Aretha Franklin", "Stevie Wonder", "Al Green", "Otis Redding"],
        "90s R&B": ["TLC", "Boyz II Men", "Aaliyah", "Destiny's Child", "Usher"],
    },
    "Country": {
        "Classic Country": ["Johnny Cash", "Dolly Parton", "Willie Nelson", "Patsy Cline", "Merle Haggard"],
        "Contemporary Country": ["Morgan Wallen", "Luke Combs", "Luke Bryan", "Jason Aldean", "Kenny Chesney"],
        "Country Pop": ["Shania Twain", "Carrie Underwood", "Kacey Musgraves", "Kelsea Ballerini", "Faith Hill"],
        "Outlaw & Americana": ["Chris Stapleton", "Zach Bryan", "Tyler Childers", "Sturgill Simpson", "Waylon Jennings"],
        "Bluegrass": ["Alison Krauss", "Billy Strings", "Old Crow Medicine Show", "The Avett Brothers", "Nickel Creek"],
    },
    "Electronic": {
        "French House": ["Daft Punk", "Justice", "Cassius", "Breakbot", "Modjo"],
        "Trip Hop": ["Massive Attack", "Portishead", "Tricky", "Zero 7", "Morcheeba"],
        "Ambient & IDM": ["Aphex Twin", "Boards of Canada", "Brian Eno", "Four Tet", "Bonobo"],
        "Synthwave": ["The Midnight", "Kavinsky", "FM-84", "Gunship", "Timecop1983"],
        "UK Garage": ["Disclosure", "Fred again..", "Jamie xx", "Craig David", "MJ Cole"],
    },
    "EDM": {
        "Big Room House": ["Martin Garrix", "Swedish House Mafia", "Avicii", "Hardwell", "Alesso"],
        "Dubstep": ["Skrillex", "Excision", "Subtronics", "Zeds Dead", "Rusko"],
        "Melodic Bass": ["ILLENIUM", "Flume", "San Holo", "Seven Lions", "Said The Sky"],
        "Tech House": ["John Summit", "FISHER", "Chris Lake", "Dom Dolla", "Mau P"],
        "Trance": ["Armin van Buuren", "Above & Beyond", "Tiësto", "Paul van Dyk", "Ferry Corsten"],
    },
    "Jazz": {
        "Bebop": ["Charlie Parker", "Dizzy Gillespie", "Thelonious Monk", "Bud Powell", "Sonny Rollins"],
        "Cool Jazz": ["Miles Davis", "Chet Baker", "Dave Brubeck", "Stan Getz", "Gerry Mulligan"],
        "Swing & Big Band": ["Duke Ellington", "Count Basie", "Benny Goodman", "Glenn Miller", "Ella Fitzgerald"],
        "Jazz Fusion": ["Herbie Hancock", "Weather Report", "Chick Corea", "Snarky Puppy", "Pat Metheny"],
        "Vocal Jazz": ["Billie Holiday", "Frank Sinatra", "Nina Simone", "Sarah Vaughan", "Norah Jones"],
    },
}

# Catch mistakes when either list is edited: every genre and sub-genre Clef can choose
# needs artists, and every list here must name a sub-genre Clef knows
for _genre, _subgenres in SUBGENRES.items():
    assert set(SUBGENRE_ARTISTS.get(_genre, {})) == set(_subgenres), f"{_genre}: sub-genres don't match endpoint/handler.py"
    for _subgenre, _artists in SUBGENRE_ARTISTS[_genre].items():
        assert _artists, f"{_genre} / {_subgenre}: no artists"
assert set(SUBGENRE_ARTISTS) == set(SUBGENRES), "genres don't match endpoint/handler.py"
