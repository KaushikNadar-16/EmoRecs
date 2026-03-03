"""
Recommendation Page for EmoRecs
────────────────────────────────
Shows personalised Books, Movies, Music, and Games recommendations
based on the detected emotion.  Content is fetched live from free
public APIs (no API keys required):

  • Books   – Open Library Search API
  • Movies  – Curated expert picks (always available)
  • Music   – iTunes Search API
  • Games   – FreeToGame API
"""

import streamlit as st
import requests
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

# Persistent HTTP session — reuses TCP connections across requests
_http_session = requests.Session()
_http_session.headers.update({
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "EmoRecs/1.0 (Emotion-Based Recommendation System; Student Project)",
})


# ━━━━━━━━━━━━  MAIN PAGE UI ━━━━━━━━━━━━━
def main():
    st.title("🎬 Emotion-Based Recommendations")
    st.markdown("Get personalized books, movies, music, and games based on your detected emotion.")

    # Example: Get detected emotion from session or user input
    detected_emotion = st.session_state.get("detected_emotion", None)
    if not detected_emotion:
        detected_emotion = st.selectbox("Select your emotion:", list(EMOTION_KEYWORDS.keys()))
        st.session_state["detected_emotion"] = detected_emotion

    st.header(f"Detected Emotion: {detected_emotion.title()}")

    # Fetch recommendations for each category
    st.subheader("📚 Book Recommendations")
    book_results = fetch_books(EMOTION_KEYWORDS[detected_emotion]["books"])
    for book in book_results:
        st.write(f"- {book}")

    st.subheader("🎵 Music Recommendations")
    music_results = fetch_music(EMOTION_KEYWORDS[detected_emotion]["music"])
    for music in music_results:
        st.write(f"- {music}")

    st.subheader("🎮 Game Recommendations")
    game_results = fetch_games(EMOTION_KEYWORDS[detected_emotion]["game_tags"])
    for game in game_results:
        st.write(f"- {game}")

    st.subheader("🎥 Movie Recommendations")
    movie_results = fetch_movies(detected_emotion)
    for movie in movie_results:
        st.write(f"- {movie}")

# Entry point for running standalone
if __name__ == "__main__":
    main()

# --- API fetch functions ---
def fetch_books(keywords):
    results = []
    for kw in keywords[:2]:
        url = f"https://openlibrary.org/search.json?q={quote_plus(kw)}&limit=3"
        try:
            resp = _http_session.get(url, timeout=5)
            data = resp.json()
            for doc in data.get("docs", [])[:2]:
                title = doc.get("title", "Unknown Title")
                author = doc.get("author_name", ["Unknown Author"])[0]
                results.append(f"{title} by {author}")
        except Exception:
            continue
    return results or ["No results found."]

def fetch_music(keywords):
    results = []
    for kw in keywords[:2]:
        url = f"https://itunes.apple.com/search?term={quote_plus(kw)}&entity=song&limit=3"
        try:
            resp = _http_session.get(url, timeout=5)
            data = resp.json()
            for track in data.get("results", [])[:2]:
                results.append(f"{track.get('trackName', 'Unknown Song')} by {track.get('artistName', 'Unknown Artist')}")
        except Exception:
            continue
    return results or ["No results found."]

def fetch_games(tags):
    results = []
    for tag in tags[:2]:
        url = f"https://www.freetogame.com/api/games?category={quote_plus(tag)}"
        try:
            resp = _http_session.get(url, timeout=5)
            data = resp.json()
            for game in data[:2]:
                results.append(f"{game.get('title', 'Unknown Game')} ({game.get('genre', 'Unknown Genre')})")
        except Exception:
            continue
    return results or ["No results found."]

def fetch_movies(emotion):
    # Curated picks for now, can be replaced with API
    curated = {
        "happy": ["3 Idiots", "Chennai Express", "Queen"],
        "sad": ["Taare Zameen Par", "Masaan", "The Lunchbox"],
        "angry": ["Gangs of Wasseypur", "Singham", "Sholay"],
        "fear": ["Tumbbad", "Pari", "Raat"],
        "surprise": ["Andhadhun", "Kahaani", "Drishyam"],
        "disgust": ["Article 15", "Pink", "Talvar"],
    }
    return curated.get(emotion, ["No results found."])

EMOTION_KEYWORDS = {
    "happy": {
        "books":  ["feel good fiction", "comedy novel", "happiness", "humorous stories", "Ruskin Bond", "R K Narayan Malgudi", "funny Indian stories"],
        "music":  ["Bollywood happy songs", "Arijit Singh happy", "Badshah party",           # Hindi
                    "Anirudh Ravichander", "Dhanush Tamil hits", "Tamil kuthu songs"],        # Tamil
        "game_tags": ["mmorpg", "social", "sports"],
    },
    "sad": {
        "books":  ["inspirational stories", "self help motivation", "uplifting novel", "healing", "Chetan Bhagat", "wings of fire APJ Abdul Kalam", "Indian motivational stories"],
        "music":  ["Arijit Singh sad", "bollywood sad songs", "Shreya Ghoshal sad",           # Hindi
                    "Sid Sriram Tamil", "Anirudh sad songs", "GV Prakash sad Tamil"],          # Tamil
        "game_tags": ["card", "turn-based", "strategy"],
    },
    "angry": {
        "books":  ["anger management", "mindfulness", "peace meditation", "stoicism", "Bhagavad Gita", "Swami Vivekananda", "Indian warrior stories"],
        "music":  ["Raftaar rap", "Emiway Bantai", "Divine rapper India",                     # Hindi
                    "Arivu Tamil rap", "Hiphop Tamizha", "Brodha V"],                         # Tamil
        "game_tags": ["shooter", "fighting", "battle-royale"],
    },
    "fear": {
        "books":  ["courage stories", "bravery fiction", "overcoming fear", "self confidence", "Panchatantra stories", "Indian mythology courage", "adventure India"],
        "music":  ["AR Rahman peaceful", "bollywood sufi", "Indian classical flute",          # Hindi
                    "Ilaiyaraaja melody", "Bombay Jayashri", "SPB Tamil songs"],               # Tamil
        "game_tags": ["sandbox", "open-world", "survival"],
    },
    "surprise": {
        "books":  ["mystery thriller", "plot twist", "suspense novel", "sci fi fiction", "Indian thriller", "Ravinder Singh", "Indian mystery fiction"],
        "music":  ["Nucleya", "AP Dhillon", "Prateek Kuhad",                                 # Hindi
                    "Anirudh Ravichander hits", "Hiphop Tamizha remix", "Yuvan Shankar Raja mass"],  # Tamil
        "game_tags": ["strategy", "card", "turn-based"],
    },
    "disgust": {
        "books":  ["nature beauty", "travel adventure", "feel good", "cooking recipes", "Indian cooking", "travel India", "Indian art culture"],
        "music":  ["Jagjit Singh ghazal", "Lata Mangeshkar", "Kishore Kumar",                 # Hindi
                    "Ilaiyaraaja classic Tamil", "SPB melody hits", "MS Subbulakshmi"],        # Tamil
        "game_tags": ["sandbox", "survival", "social"],
    },
    "neutral": {
        "books":  ["bestseller fiction", "popular science", "biography memoir", "classic novel", "Amish Tripathi", "Sudha Murthy", "Indian bestseller"],
        "music":  ["Arijit Singh", "Pritam bollywood", "latest hindi songs",                  # Hindi
                    "Anirudh latest", "Sid Sriram", "latest Tamil songs"],                     # Tamil
        "game_tags": ["mmorpg", "open-world", "racing"],
    },
}

EMOTION_EMOJI = {
    "angry": "😠", "disgust": "🤢", "fear": "😨",
    "happy": "😊", "sad": "😢", "surprise": "😲", "neutral": "😐",
}

EMOTION_TAGLINES = {
    "happy":    "You look happy! Here's some fun content to keep the good vibes going 🎉",
    "sad":      "Feeling down? Here are some uplifting picks to brighten your mood 💛",
    "angry":    "Let's channel that energy! Here are some intense and calming picks 🔥",
    "fear":     "Nothing to worry about — here's some light and comforting content 🌈",
    "surprise": "Surprised? Explore something unexpected and exciting! ✨",
    "disgust":  "Let's shift the mood — here's some refreshing and pleasant content 🌿",
    "neutral":  "Feeling balanced — check out today's trending picks across categories 🌟",
}

# ━━━━━━━━━━━━  CURATED MOVIE DATABASE  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# High-quality recommendations — always available, no API key needed.
# Poster images served from TMDB's public CDN.

_CURATED_MOVIES = {
    "happy": [
        {"title": "3 Idiots", "year": "2009", "rating": 8.4, "overview": "Two friends search for their long-lost college pal, recalling their days of engineering fun and rebellion.", "poster": "https://image.tmdb.org/t/p/w300/66A9MqXOyVFCssoloscw79z8Tew.jpg", "url": "https://www.imdb.com/title/tt1187043/"},
        {"title": "Zindagi Na Milegi Dobara", "year": "2011", "rating": 8.0, "overview": "Three friends go on a bachelor road trip through Spain, rediscovering life and friendship.", "poster": "https://image.tmdb.org/t/p/w300/sDi9i4sFMeLwIqGCkmFiq4qPAde.jpg", "url": "https://www.imdb.com/title/tt1562872/"},
        {"title": "PK", "year": "2014", "rating": 8.1, "overview": "An alien on Earth questions religious dogma and blind faith through innocent, hilarious observations.", "poster": "https://image.tmdb.org/t/p/w300/mHOTBzGFuMbMsVOnHiyQqpRbkOs.jpg", "url": "https://www.imdb.com/title/tt2338151/"},
        {"title": "Forrest Gump", "year": "1994", "rating": 8.8, "overview": "The presidencies of Kennedy and Johnson through the eyes of an Alabama man with an IQ of 75.", "poster": "https://image.tmdb.org/t/p/w300/arw2vcBveWOVZr6pxd9XTd1TdQa.jpg", "url": "https://www.imdb.com/title/tt0109830/"},
        {"title": "Chhichhore", "year": "2019", "rating": 7.8, "overview": "A father narrates his fun-filled college days to inspire his hospitalised son about winning and losing.", "poster": "https://image.tmdb.org/t/p/w300/uH0ccYYIlLOx73yDj5IpBLzaV5a.jpg", "url": "https://www.imdb.com/title/tt9052870/"},
        {"title": "Inside Out", "year": "2015", "rating": 8.1, "overview": "After young Riley is uprooted from her life, her emotions conflict on how best to navigate a new city.", "poster": "https://image.tmdb.org/t/p/w300/2H1TmgdfNtsKlU9jKdeNyYL5y8T.jpg", "url": "https://www.imdb.com/title/tt2096673/"},
        {"title": "Hera Pheri", "year": "2000", "rating": 8.2, "overview": "Three unemployed men get a wrong-number call offering ransom money, leading to a comedy of errors.", "poster": "https://image.tmdb.org/t/p/w300/6fJqlPiLgCaSMqjmiKqMijdBvNS.jpg", "url": "https://www.imdb.com/title/tt0242519/"},
        {"title": "The Grand Budapest Hotel", "year": "2014", "rating": 8.1, "overview": "A concierge at a famous hotel becomes the prime suspect in a priceless painting theft.", "poster": "https://image.tmdb.org/t/p/w300/eWDyYPOshvGiInJx4MyQgJlcDxm.jpg", "url": "https://www.imdb.com/title/tt2278388/"},
    ],
    "sad": [
        {"title": "Taare Zameen Par", "year": "2007", "rating": 8.4, "overview": "An art teacher suspects a dyslexic child has been harshly misjudged and tries to help him.", "poster": "https://image.tmdb.org/t/p/w300/qJlMlSA5YKMMHQ8YL8xk6rOXJCR.jpg", "url": "https://www.imdb.com/title/tt0986264/"},
        {"title": "Dil Bechara", "year": "2020", "rating": 7.4, "overview": "A terminally ill girl's life changes when she meets a boy who lives life to the fullest.", "poster": "https://image.tmdb.org/t/p/w300/vP3MiPNajkMkunnq2FFghJsc12e.jpg", "url": "https://www.imdb.com/title/tt5765162/"},
        {"title": "The Shawshank Redemption", "year": "1994", "rating": 9.3, "overview": "Two imprisoned men bond over years, finding solace and eventual redemption through kindness.", "poster": "https://image.tmdb.org/t/p/w300/9cjIGRiQvEYqQiMlBQ9Si68vNFL.jpg", "url": "https://www.imdb.com/title/tt0111161/"},
        {"title": "Masaan", "year": "2015", "rating": 8.1, "overview": "Four lives in Varanasi intersect as they navigate love, loss, and the weight of society.", "poster": "https://image.tmdb.org/t/p/w300/xOdMd3GXl4X2dqMIBxBJLXLqwpN.jpg", "url": "https://www.imdb.com/title/tt4635372/"},
        {"title": "Coco", "year": "2017", "rating": 8.4, "overview": "A boy journeys to the Land of the Dead to unlock the real story behind his family history.", "poster": "https://image.tmdb.org/t/p/w300/gGEsBPAijhVUFoiNpgZXqRVWJt2.jpg", "url": "https://www.imdb.com/title/tt2380307/"},
        {"title": "Rang De Basanti", "year": "2006", "rating": 8.1, "overview": "University students in Delhi relive India's freedom struggle and are inspired to act against corruption.", "poster": "https://image.tmdb.org/t/p/w300/aGhRNUiIkUfTcON3HWBI0L7f8qB.jpg", "url": "https://www.imdb.com/title/tt0405508/"},
        {"title": "The Pursuit of Happyness", "year": "2006", "rating": 8.0, "overview": "A struggling salesman takes custody of his son as he tackles a life-changing professional career.", "poster": "https://image.tmdb.org/t/p/w300/lBYOKAMcxIvuk9s9hMjBPIqUec.jpg", "url": "https://www.imdb.com/title/tt0454921/"},
        {"title": "Wonder", "year": "2017", "rating": 8.0, "overview": "A boy with facial differences attends school for the first time and inspires everyone around him.", "poster": "https://image.tmdb.org/t/p/w300/o3bNMlnOKbc1lbMIE7MZmG75GiI.jpg", "url": "https://www.imdb.com/title/tt2543472/"},
    ],
    "angry": [
        {"title": "Dangal", "year": "2016", "rating": 8.4, "overview": "A former wrestler trains his daughters to become India's first world-class female wrestlers.", "poster": "https://image.tmdb.org/t/p/w300/fYwOgLqNLkfqEbLhOecLqY8jOnr.jpg", "url": "https://www.imdb.com/title/tt5074352/"},
        {"title": "Pushpa: The Rise", "year": "2021", "rating": 7.6, "overview": "A laborer rises through the ranks of a red sandalwood smuggling syndicate, facing ruthless enemies.", "poster": "https://image.tmdb.org/t/p/w300/psyehIDiswMqtHNeweFSAEoXjka.jpg", "url": "https://www.imdb.com/title/tt9078374/"},
        {"title": "KGF: Chapter 2", "year": "2022", "rating": 7.8, "overview": "Rocky's reign over the Kolar Gold Fields is challenged by Adheera's return and government pressure.", "poster": "https://image.tmdb.org/t/p/w300/4zKx2XEXuJM1bYEiAUW5VwUpmTe.jpg", "url": "https://www.imdb.com/title/tt10322938/"},
        {"title": "The Dark Knight", "year": "2008", "rating": 9.0, "overview": "Batman faces one of the greatest psychological tests of his ability to fight injustice.", "poster": "https://image.tmdb.org/t/p/w300/qJ2tW6WMUDux911BTUgMEDaVVEB.jpg", "url": "https://www.imdb.com/title/tt0468569/"},
        {"title": "Ghajini", "year": "2008", "rating": 7.1, "overview": "A businessman with short-term memory loss hunts for the man who murdered his girlfriend.", "poster": "https://image.tmdb.org/t/p/w300/xGp2O6xtWXCLmHeCiEJrNa5NYRb.jpg", "url": "https://www.imdb.com/title/tt1166100/"},
        {"title": "Whiplash", "year": "2014", "rating": 8.5, "overview": "A drummer endures extremes from an instructor who stops at nothing to unlock his potential.", "poster": "https://image.tmdb.org/t/p/w300/7fn624j5lj3xTme2SgiLCeuedmO.jpg", "url": "https://www.imdb.com/title/tt2582802/"},
        {"title": "Sultan", "year": "2016", "rating": 6.7, "overview": "A wrestling champion from Haryana goes on a journey of redemption after losing everything.", "poster": "https://image.tmdb.org/t/p/w300/s2b5M4IOlMBqJeGLvp58sV1AhFD.jpg", "url": "https://www.imdb.com/title/tt4832640/"},
        {"title": "Mad Max: Fury Road", "year": "2015", "rating": 8.1, "overview": "In a post-apocalyptic wasteland, a woman rebels against a tyrannical ruler.", "poster": "https://image.tmdb.org/t/p/w300/8tZYtuWezp8JbcsvHYO0O46tFbo.jpg", "url": "https://www.imdb.com/title/tt1392190/"},
    ],
    "fear": [
        {"title": "Bajrangi Bhaijaan", "year": "2015", "rating": 8.0, "overview": "An Indian man with a heart of gold helps a mute Pakistani girl find her way back home.", "poster": "https://image.tmdb.org/t/p/w300/iZtbr1EjPRfOElAFjsqa0LhYIup.jpg", "url": "https://www.imdb.com/title/tt3863552/"},
        {"title": "Finding Nemo", "year": "2003", "rating": 8.2, "overview": "A clown fish braves the ocean to find his son, overcoming every fear along the way.", "poster": "https://image.tmdb.org/t/p/w300/eHuGQ10FUzJ1cPs93AMHh8wYKgp.jpg", "url": "https://www.imdb.com/title/tt0266543/"},
        {"title": "Queen", "year": "2014", "rating": 8.2, "overview": "A sheltered Delhi girl goes on her honeymoon alone after her wedding is called off, finding herself.", "poster": "https://image.tmdb.org/t/p/w300/6tHGn2hMC7IHGKCZPELPPFZR2q7.jpg", "url": "https://www.imdb.com/title/tt3322420/"},
        {"title": "Spirited Away", "year": "2001", "rating": 8.6, "overview": "A young girl navigates a world of spirits after her parents are transformed into pigs.", "poster": "https://image.tmdb.org/t/p/w300/39wmItIWsg5sZMyRUHLkWBcuVCM.jpg", "url": "https://www.imdb.com/title/tt0245429/"},
        {"title": "Munna Bhai M.B.B.S.", "year": "2003", "rating": 8.0, "overview": "A gangster goes to medical school to fulfil his father's dream, spreading warmth everywhere.", "poster": "https://image.tmdb.org/t/p/w300/qUdMUkWVllWuR1ePJfGLHzOpXJ9.jpg", "url": "https://www.imdb.com/title/tt0374887/"},
        {"title": "How to Train Your Dragon", "year": "2010", "rating": 8.1, "overview": "A young Viking befriends a dragon instead of fighting it, changing both their worlds.", "poster": "https://image.tmdb.org/t/p/w300/ygGmAO60t8GyqUo9xYeYxSZAR3b.jpg", "url": "https://www.imdb.com/title/tt0892769/"},
        {"title": "Swades", "year": "2004", "rating": 8.2, "overview": "An NRI NASA scientist visits his homeland and is moved to make a difference in rural India.", "poster": "https://image.tmdb.org/t/p/w300/3EFrfFGp2kXpXVcJQgqQr2IXjey.jpg", "url": "https://www.imdb.com/title/tt0367110/"},
        {"title": "Big Hero 6", "year": "2014", "rating": 7.8, "overview": "A robotics prodigy and his inflatable robot uncover a criminal plot in San Fransokyo.", "poster": "https://image.tmdb.org/t/p/w300/2mxS4wUimwlLmI1xp6QW6Ny0hxR.jpg", "url": "https://www.imdb.com/title/tt2245084/"},
    ],
    "surprise": [
        {"title": "Andhadhun", "year": "2018", "rating": 8.3, "overview": "A blind pianist unwittingly becomes entangled in a number of murders in this twisty thriller.", "poster": "https://image.tmdb.org/t/p/w300/lz090FMrJ4QX0jDq1fRaFJLghoj.jpg", "url": "https://www.imdb.com/title/tt8108198/"},
        {"title": "Drishyam", "year": "2015", "rating": 8.2, "overview": "A man goes to extreme lengths to protect his family after they are involved in a crime.", "poster": "https://image.tmdb.org/t/p/w300/qp5sSqOqxJvgV70zKCafLg0ZjNE.jpg", "url": "https://www.imdb.com/title/tt4430212/"},
        {"title": "Inception", "year": "2010", "rating": 8.8, "overview": "A thief who enters dreams is given the inverse task of planting an idea into the mind of a CEO.", "poster": "https://image.tmdb.org/t/p/w300/edv5CZvWj09upOsy2Y6IwDhK8bt.jpg", "url": "https://www.imdb.com/title/tt1375666/"},
        {"title": "Kahaani", "year": "2012", "rating": 8.1, "overview": "A pregnant woman searching for her missing husband in Kolkata uncovers a deadly conspiracy.", "poster": "https://image.tmdb.org/t/p/w300/sOh2wJTDxjwQGNqwJvkJKyqFMnW.jpg", "url": "https://www.imdb.com/title/tt1821480/"},
        {"title": "The Matrix", "year": "1999", "rating": 8.7, "overview": "A computer hacker learns that reality as he knows it is a simulation created by machines.", "poster": "https://image.tmdb.org/t/p/w300/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg", "url": "https://www.imdb.com/title/tt0133093/"},
        {"title": "Talaash", "year": "2012", "rating": 7.2, "overview": "A troubled police officer investigates a Bollywood star's death and finds a supernatural twist.", "poster": "https://image.tmdb.org/t/p/w300/sHXRifW96J9CwKgwObqOZv8DQZO.jpg", "url": "https://www.imdb.com/title/tt1787988/"},
        {"title": "Interstellar", "year": "2014", "rating": 8.7, "overview": "A team of explorers travel through a wormhole in space to ensure humanity's survival.", "poster": "https://image.tmdb.org/t/p/w300/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg", "url": "https://www.imdb.com/title/tt0816692/"},
        {"title": "Everything Everywhere All at Once", "year": "2022", "rating": 7.8, "overview": "A laundromat owner discovers she can access alternate universe versions of herself.", "poster": "https://image.tmdb.org/t/p/w300/w3LxiVYdWWRvEVdn5RYq6jIqkb1.jpg", "url": "https://www.imdb.com/title/tt6710474/"},
    ],
    "disgust": [
        {"title": "Lunchbox", "year": "2013", "rating": 7.8, "overview": "A mistaken lunch delivery connects a lonely housewife and an aging widower through notes in Mumbai.", "poster": "https://image.tmdb.org/t/p/w300/mLrQMqyZgLeP8FrT5LCobKAiqmK.jpg", "url": "https://www.imdb.com/title/tt2350496/"},
        {"title": "The Hundred-Foot Journey", "year": "2014", "rating": 7.3, "overview": "An Indian family opens a restaurant opposite a French Michelin-starred restaurant.", "poster": "https://image.tmdb.org/t/p/w300/b0MzrsKwJjwCr8Fk7W3bKM5k1cS.jpg", "url": "https://www.imdb.com/title/tt2980648/"},
        {"title": "WALL-E", "year": "2008", "rating": 8.4, "overview": "A lonely robot on a future Earth finds a new purpose when a sleek search robot arrives.", "poster": "https://image.tmdb.org/t/p/w300/hbhFnRzzg6ZDmm8YAmxBnQpQIPh.jpg", "url": "https://www.imdb.com/title/tt0910970/"},
        {"title": "English Vinglish", "year": "2012", "rating": 7.8, "overview": "A housewife enrols in an English class to gain respect from her family that undervalue her.", "poster": "https://image.tmdb.org/t/p/w300/8RJxG1VVN4gk0dvSJLKrI0EHFRw.jpg", "url": "https://www.imdb.com/title/tt2181931/"},
        {"title": "Amelie", "year": "2001", "rating": 8.3, "overview": "A shy waitress decides to change the lives of those around her for the better.", "poster": "https://image.tmdb.org/t/p/w300/nSxDa3ppUjBbGSZLOYgvCMOmPxz.jpg", "url": "https://www.imdb.com/title/tt0211915/"},
        {"title": "Piku", "year": "2015", "rating": 7.6, "overview": "A quirky comedy-drama about an architect dealing with her aging, eccentric father in Kolkata.", "poster": "https://image.tmdb.org/t/p/w300/ouUNlXULgzNj2gbZYt3SZjjMTf3.jpg", "url": "https://www.imdb.com/title/tt3767372/"},
        {"title": "Howl's Moving Castle", "year": "2004", "rating": 8.2, "overview": "A young woman cursed with old age ventures into a magical moving castle run by a wizard.", "poster": "https://image.tmdb.org/t/p/w300/TkTPELv4kC3u1V2of6EGrlVgeMk.jpg", "url": "https://www.imdb.com/title/tt0347149/"},
        {"title": "Chef", "year": "2014", "rating": 7.3, "overview": "A chef starts a food truck after losing his job, reigniting his passion for cooking.", "poster": "https://image.tmdb.org/t/p/w300/eHLBMtnFDnCrQisjk3Nmq4dXNjh.jpg", "url": "https://www.imdb.com/title/tt2883512/"},
    ],
    "neutral": [
        {"title": "Lagaan", "year": "2001", "rating": 8.1, "overview": "Villagers in colonial India stake their future on a cricket match against their British rulers.", "poster": "https://image.tmdb.org/t/p/w300/gIFhMsDJCTlvOjVKpdn5r47SXUF.jpg", "url": "https://www.imdb.com/title/tt0169102/"},
        {"title": "The Imitation Game", "year": "2014", "rating": 8.0, "overview": "Alan Turing builds a machine to crack the Nazi Enigma code during World War II.", "poster": "https://image.tmdb.org/t/p/w300/zSqJ1qFq8NXFfi7JeIYMlzyR0dx.jpg", "url": "https://www.imdb.com/title/tt2084970/"},
        {"title": "Pad Man", "year": "2018", "rating": 7.8, "overview": "A man from rural India creates a low-cost sanitary pad machine, revolutionising women's hygiene.", "poster": "https://image.tmdb.org/t/p/w300/2cwBJBYmqIGSjgClJDjBjfQHRth.jpg", "url": "https://www.imdb.com/title/tt7218518/"},
        {"title": "The Martian", "year": "2015", "rating": 8.0, "overview": "An astronaut stranded on Mars must improvise to survive while NASA works to bring him home.", "poster": "https://image.tmdb.org/t/p/w300/5BHuvQ6p9kfc091Z8RiFNhCwL4b.jpg", "url": "https://www.imdb.com/title/tt3659388/"},
        {"title": "Super 30", "year": "2019", "rating": 7.3, "overview": "A math genius from Bihar coaches underprivileged students for India's toughest engineering exam.", "poster": "https://image.tmdb.org/t/p/w300/plJWZpJidbPMCngT7SiGY37hsvA.jpg", "url": "https://www.imdb.com/title/tt7485048/"},
        {"title": "Bohemian Rhapsody", "year": "2018", "rating": 7.9, "overview": "The story of the legendary rock band Queen and frontman Freddie Mercury.", "poster": "https://image.tmdb.org/t/p/w300/lHu1wtNaczFPGFDTrjCSzeLPTKN.jpg", "url": "https://www.imdb.com/title/tt1727824/"},
        {"title": "Bhaag Milkha Bhaag", "year": "2013", "rating": 7.8, "overview": "The true story of India's legendary athlete Milkha Singh and his journey to Olympic glory.", "poster": "https://image.tmdb.org/t/p/w300/rlFKriCrKYSsN2M33mdr0O55MBh.jpg", "url": "https://www.imdb.com/title/tt2356180/"},
        {"title": "Dune", "year": "2021", "rating": 8.0, "overview": "Paul Atreides unites with the Fremen people of Arrakis to fight for the future.", "poster": "https://image.tmdb.org/t/p/w300/d5NXSklXo0qyIYkgV94XAgMIckC.jpg", "url": "https://www.imdb.com/title/tt1160419/"},
    ],
}


# ━━━━━━━━━━━━━━  API FETCHERS  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _safe_get(url, params=None, timeout=4):
    """GET with timeout, returns JSON or None."""
    try:
        r = _http_session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ── BOOKS (Open Library) ──────────────────────────────────────────────
def fetch_books(emotion: str, limit: int = 8) -> list[dict]:
    """Search Open Library for books matching the emotion keywords."""
    keywords = EMOTION_KEYWORDS.get(emotion, EMOTION_KEYWORDS["neutral"])["books"]
    query = random.choice(keywords)
    data = _safe_get(
        "https://openlibrary.org/search.json",
        params={"q": query, "limit": limit,
                "fields": "key,title,author_name,cover_i,first_publish_year,subject"},
    )
    if not data or "docs" not in data:
        return []

    results = []
    for doc in data["docs"][:limit]:
        cover_id = doc.get("cover_i")
        cover_url = (f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                     if cover_id else None)
        results.append({
            "title":  doc.get("title", "Unknown"),
            "author": ", ".join(doc.get("author_name", [])[:2]) or "Unknown",
            "year":   doc.get("first_publish_year", ""),
            "cover":  cover_url,
            "url":    f"https://openlibrary.org{doc['key']}" if "key" in doc else "#",
        })
    return results


# ── MOVIE POSTER RESOLVER (Wikipedia MediaWiki API) ──────────────────
_WIKI_API = "https://en.wikipedia.org/w/api.php"

def _wiki_batch_posters(titles: list[str], size: int = 500) -> dict[str, str]:
    """Batch-fetch movie poster thumbnails from Wikipedia.
    Returns {title: poster_url} for titles that have an image.
    Uses a single HTTP request for up to 50 titles (API limit)."""
    if not titles:
        return {}
    params = {
        "action": "query",
        "titles": "|".join(titles),
        "prop": "pageimages",
        "format": "json",
        "pithumbsize": size,
        "pilicense": "any",
    }
    try:
        r = _http_session.get(_WIKI_API, params=params, timeout=4)
        if r.status_code != 200:
            return {}
        pages = r.json().get("query", {}).get("pages", {})
        result = {}
        for page in pages.values():
            title = page.get("title", "")
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                result[title.lower()] = thumb
        return result
    except Exception:
        return {}


# Wikipedia article name overrides for movies whose title doesn't
# match the Wikipedia article exactly.
_WIKI_TITLE_MAP = {
    "amelie": "Amélie",
    "howl's moving castle": "Howl's Moving Castle (film)",
    "howls moving castle": "Howl's Moving Castle (film)",
    "queen": "Queen (2013 film)",
    "talaash": "Talaash: The Answer Lies Within",
    "lunchbox": "The Lunchbox",
    "the lunchbox": "The Lunchbox",
    "coco": "Coco (2017 film)",
    "sultan": "Sultan (2016 film)",
    "dune": "Dune (2021 film)",
    "chef": "Chef (2014 film)",
    "brave": "Brave (2012 film)",
}


def _resolve_movie_posters(movies: list[dict]) -> None:
    """Resolve real poster URLs from Wikipedia for a list of movie dicts.
    Uses up to 3 batch requests for maximum coverage:
      Pass 1 — raw title (or wiki override)
      Pass 2 — title (year film)
      Pass 3 — title (film)
    Typically resolves 95%+ of posters in ~1s total."""
    # Build initial lookup titles using overrides where available
    pass1_titles = []
    pass1_map = {}  # wiki_title_lower -> movie dict
    for m in movies:
        key = m["title"].lower()
        wiki_title = _WIKI_TITLE_MAP.get(key, m["title"])
        pass1_titles.append(wiki_title)
        pass1_map[wiki_title.lower()] = m

    # Pass 1
    posters = _wiki_batch_posters(pass1_titles)
    missing = []
    for m in movies:
        key = m["title"].lower()
        wiki_key = _WIKI_TITLE_MAP.get(key, m["title"]).lower()
        if wiki_key in posters:
            m["poster"] = posters[wiki_key]
        else:
            missing.append(m)

    # Pass 2: retry with "(year film)" suffix
    if missing:
        retry2 = []
        map2 = {}
        for m in missing:
            year = m.get("year", "")
            alt = f"{m['title']} ({year} film)" if year else f"{m['title']} (film)"
            retry2.append(alt)
            map2[alt.lower()] = m
        posters2 = _wiki_batch_posters(retry2)
        still_missing = []
        for m in missing:
            year = m.get("year", "")
            alt = f"{m['title']} ({year} film)" if year else f"{m['title']} (film)"
            if alt.lower() in posters2:
                m["poster"] = posters2[alt.lower()]
            else:
                still_missing.append(m)
        missing = still_missing

    # Pass 3: retry with "(film)" suffix only
    if missing:
        retry3 = []
        map3 = {}
        for m in missing:
            alt = f"{m['title']} (film)"
            retry3.append(alt)
            map3[alt.lower()] = m
        posters3 = _wiki_batch_posters(retry3)
        for alt_key, url in posters3.items():
            m = map3.get(alt_key)
            if m:
                m["poster"] = url


# ── MOVIES (Curated Expert Picks) ─────────────────────────────────────
def fetch_movies(emotion: str, limit: int = 8) -> list[dict]:
    """Return curated movie recommendations for the given emotion.
    Posters are fetched live from Wikipedia for reliability (~0.5-1s).
    URLs point to JustWatch India so users can find where to stream
    the full movie (Netflix, Prime, Hotstar, JioCinema, etc.)."""
    movies = list(_CURATED_MOVIES.get(emotion,
                                       _CURATED_MOVIES.get("neutral", [])))
    random.shuffle(movies)
    result = movies[:limit]

    # Resolve real poster URLs from Wikipedia (1-2 batch HTTP calls)
    _resolve_movie_posters(result)

    for m in result:
        m["url"] = f"https://www.justwatch.com/in/search?q={quote_plus(m['title'])}"
    return result


# ── MUSIC (iTunes Search) ────────────────────────────────────────────
def fetch_music(emotion: str, limit: int = 8) -> list[dict]:
    """Search iTunes for music tracks matching emotion keywords.
    Uses country=IN to prioritize the Indian iTunes store."""
    keywords = EMOTION_KEYWORDS.get(emotion, EMOTION_KEYWORDS["neutral"])["music"]
    query = random.choice(keywords)
    data = _safe_get(
        "https://itunes.apple.com/search",
        params={"term": query, "media": "music", "limit": limit,
                "country": "IN"},
    )
    if not data or "results" not in data:
        return []

    results = []
    for t in data["results"][:limit]:
        artwork = t.get("artworkUrl100", "")
        # Upgrade to 300×300 if possible
        if artwork:
            artwork = artwork.replace("100x100", "300x300")
        results.append({
            "title":   t.get("trackName", "Unknown"),
            "artist":  t.get("artistName", "Unknown"),
            "album":   t.get("collectionName", ""),
            "cover":   artwork or None,
            "preview": t.get("previewUrl"),      # 30-sec AAC preview
            "url":     t.get("trackViewUrl", "#"),
        })
    return results


# ── GAMES (FreeToGame) ────────────────────────────────────────────────
def fetch_games(emotion: str, limit: int = 8) -> list[dict]:
    """Fetch free-to-play games from the FreeToGame API by category."""
    tags = EMOTION_KEYWORDS.get(emotion, EMOTION_KEYWORDS["neutral"])["game_tags"]
    tag = random.choice(tags)
    data = _safe_get(
        "https://www.freetogame.com/api/games",
        params={"category": tag, "sort-by": "popularity"},
    )
    if not data or not isinstance(data, list):
        return []

    # Pick a random slice so it feels fresh
    if len(data) > limit:
        start = random.randint(0, max(0, len(data) - limit))
        data = data[start:start + limit]

    results = []
    for g in data[:limit]:
        results.append({
            "title":    g.get("title", "Unknown"),
            "genre":    g.get("genre", ""),
            "platform": g.get("platform", ""),
            "cover":    g.get("thumbnail"),
            "overview": (g.get("short_description") or "")[:120],
            "url":      g.get("game_url", "#"),
        })
    return results


# ━━━━━━━━━━━━━━  PARALLEL FETCH  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@st.cache_data(ttl=900, show_spinner=False)
def fetch_all_recommendations(emotion: str):
    """Fetch all four categories in parallel. Cached for 5 minutes."""
    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(fetch_books, emotion):  "books",
            pool.submit(fetch_movies, emotion): "movies",
            pool.submit(fetch_music, emotion):  "music",
            pool.submit(fetch_games, emotion):  "games",
        }
        for future in as_completed(futures):
            category = futures[future]
            try:
                results[category] = future.result()
            except Exception:
                results[category] = []
    return results


# ━━━━━━━━━━━━━━  RENDER HELPERS  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _card_css():
    """Inject card styling once."""
    st.markdown("""
    <link rel="preconnect" href="https://image.tmdb.org" crossorigin>
    <link rel="preconnect" href="https://covers.openlibrary.org" crossorigin>
    <link rel="preconnect" href="https://is1-ssl.mzstatic.com" crossorigin>
    <link rel="dns-prefetch" href="https://image.tmdb.org">
    <link rel="dns-prefetch" href="https://covers.openlibrary.org">
    <link rel="dns-prefetch" href="https://is1-ssl.mzstatic.com">
    <style>
    .rec-card {
        background: rgba(255,255,255,0.07);
        border: 1px solid rgba(108,99,255,0.25);
        border-radius: 14px;
        padding: 14px;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-start;
    }
    .rec-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 24px rgba(108,99,255,0.3);
        border-color: rgba(108,99,255,0.6);
    }
    .rec-card img {
        border-radius: 10px;
        width: 100%;
        height: 280px;
        object-fit: cover;
        margin-bottom: 10px;
        background: linear-gradient(135deg, #3a3a5c, #2a2a4a);
        animation: imgPulse 1.5s ease-in-out infinite;
    }
    .rec-card img.loaded {
        animation: none;
    }
    @keyframes imgPulse {
        0%, 100% { opacity: 0.6; }
        50%      { opacity: 1; }
    }
    .rec-card .title {
        font-weight: 600;
        font-size: 0.95rem;
        color: #f5f7ff;
        margin: 6px 0 4px;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }
    .rec-card .sub {
        font-size: 0.78rem;
        color: #aaa;
        margin: 2px 0;
    }
    .rec-card .badge {
        display: inline-block;
        background: linear-gradient(135deg, #6c63ff, #00d2ff);
        color: white;
        font-size: 0.7rem;
        padding: 2px 8px;
        border-radius: 10px;
        margin-top: 4px;
    }
    a.rec-card-link {
        text-decoration: none;
        color: inherit;
        display: block;
        height: 100%;
        cursor: pointer;
    }
    a.rec-card-link:hover .rec-card {
        transform: translateY(-4px);
        box-shadow: 0 8px 24px rgba(108,99,255,0.3);
        border-color: rgba(108,99,255,0.6);
    }
    .no-img-placeholder {
        width: 100%;
        height: 280px;
        background: linear-gradient(135deg, #3a3a5c, #2a2a4a);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.5rem;
        margin-bottom: 10px;
    }
    .section-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 28px 0 14px;
        padding-bottom: 8px;
        border-bottom: 2px solid rgba(108,99,255,0.3);
    }
    .section-header h3 {
        margin: 0;
        color: #f5f7ff;
        font-size: 1.3rem;
    }
    </style>
    """, unsafe_allow_html=True)


def _render_section(title: str, icon: str, items: list[dict], category: str):
    """Render a grid of recommendation cards."""
    st.markdown(f"""
    <div class="section-header">
        <span style="font-size:1.6rem;">{icon}</span>
        <h3>{title}</h3>
        <span style="color:#aaa;font-size:0.85rem;margin-left:auto;">
            {len(items)} result{'s' if len(items) != 1 else ''}
        </span>
    </div>""", unsafe_allow_html=True)

    if not items:
        st.info(f"Could not fetch {title.lower()} right now. Try again later!")
        return

    cols = st.columns(4)
    for i, item in enumerate(items[:8]):
        with cols[i % 4]:
            img_html = ""
            placeholders = {"books": "📚", "movies": "🎬",
                            "music": "🎵", "games": "🎮"}
            placeholder_icon = placeholders.get(category, "📦")
            fallback_div = (f'<div class="no-img-placeholder">{placeholder_icon}</div>')
            if item.get("cover") or item.get("poster"):
                img_url = item.get("cover") or item.get("poster")
                # Upgrade TMDB w300 → w500 for sharper posters
                if "image.tmdb.org" in img_url:
                    img_url = img_url.replace("/w300/", "/w500/")
                img_html = (
                    f'<img src="{img_url}" alt="{item["title"]}" '
                    f'referrerpolicy="no-referrer" loading="eager" '
                    f'decoding="async" fetchpriority="high" '
                    f'onload="this.classList.add(\'loaded\')" '
                    f'onerror="this.style.display=\'none\';'
                    f'this.nextElementSibling.style.display=\'flex\'"/>'
                    f'<div class="no-img-placeholder" style="display:none">{placeholder_icon}</div>'
                )
            else:
                img_html = fallback_div

            subtitle = ""
            if category == "books":
                subtitle = f'{item.get("author", "")}'
                if item.get("year"):
                    subtitle += f' · {item["year"]}'
            elif category == "movies":
                parts = []
                if item.get("year"):
                    parts.append(item["year"])
                if item.get("rating"):
                    parts.append(f"⭐ {item['rating']}")
                subtitle = " · ".join(str(p) for p in parts)
            elif category == "music":
                subtitle = item.get("artist", "")
                if item.get("album"):
                    subtitle += f' · {item["album"]}'
            elif category == "games":
                parts = []
                if item.get("genre"):
                    parts.append(item["genre"])
                if item.get("platform"):
                    parts.append(item["platform"])
                subtitle = " · ".join(str(p) for p in parts)

            badge = ""
            if category == "games" and item.get("genre"):
                badge = f'<span class="badge">{item["genre"]}</span>'
            elif category == "movies" and item.get("overview"):
                badge = (f'<p class="sub" style="font-size:0.72rem;'
                         f'margin-top:4px;">{item["overview"]}</p>')

            link = item.get("url") or item.get("poster") or "#"

            if category in ("books", "movies", "games") and link != "#":
                card_html = f"""
                <a class="rec-card-link" href="{link}" target="_blank">
                <div class="rec-card">
                    {img_html}
                    <div class="title">{item["title"]}</div>
                    <p class="sub">{subtitle}</p>
                    {badge}
                </div>
                </a>
                """
            else:
                card_html = f"""
                <div class="rec-card">
                    {img_html}
                    <div class="title">{item["title"]}</div>
                    <p class="sub">{subtitle}</p>
                    {badge}
                </div>
                """
            st.markdown(card_html, unsafe_allow_html=True)

            # Audio preview for music
            if category == "music" and item.get("preview"):
                st.audio(item["preview"], format="audio/mp4")


# ━━━━━━━━━━━━━━  MAIN  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main(detected_emotion: str = None):
    """
    Recommendation page entry-point — called from app.py.
    `detected_emotion` is passed from the emotion detection flow.
    """
    _card_css()

    # Determine emotion to use
    emotion = detected_emotion or st.session_state.get("detected_emotion")

    # Header
    st.markdown("""
    <div style="text-align:center;padding:20px 0 8px;">
        <h1 style="color:#f5f7ff;margin-bottom:4px;">
            🎯 Personalised Recommendations
        </h1>
        <p style="color:#c8c8c8;font-size:1rem;max-width:650px;margin:0 auto;">
            Content curated based on your detected emotion, fetched live from the internet.
        </p>
    </div>""", unsafe_allow_html=True)

    # If no emotion detected, let user pick manually
    if not emotion:
        st.warning("No emotion detected yet. You can select one manually below, "
                    "or go to **Emotion Detection** first.")
        manual = st.selectbox(
            "Choose an emotion:",
            options=list(EMOTION_KEYWORDS.keys()),
            format_func=lambda e: f"{EMOTION_EMOJI.get(e, '')} {e.capitalize()}",
        )
        if st.button("Get Recommendations", use_container_width=True):
            emotion = manual
            st.session_state.detected_emotion = emotion
        else:
            return

    emoji = EMOTION_EMOJI.get(emotion, "🎯")
    tagline = EMOTION_TAGLINES.get(emotion, "Here are your recommendations!")

    # Emotion banner
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,rgba(108,99,255,0.25),rgba(0,210,255,0.15));
                border:1px solid rgba(108,99,255,0.35);border-radius:16px;
                padding:20px 28px;margin:10px 0 20px;text-align:center;">
        <p style="font-size:2.4rem;margin:0;">{emoji}</p>
        <h2 style="color:#f5f7ff;margin:4px 0;">Detected: {emotion.capitalize()}</h2>
        <p style="color:#d0d0d0;font-size:0.95rem;margin:0;">{tagline}</p>
    </div>""", unsafe_allow_html=True)

    # Option to pick a different emotion
    with st.expander("🔄 Choose a different emotion"):
        new_emotion = st.selectbox(
            "Emotion:",
            options=list(EMOTION_KEYWORDS.keys()),
            index=list(EMOTION_KEYWORDS.keys()).index(emotion),
            format_func=lambda e: f"{EMOTION_EMOJI.get(e, '')} {e.capitalize()}",
            key="rec_emotion_override",
        )
        if st.button("Update Recommendations", key="rec_update_btn"):
            emotion = new_emotion
            st.session_state.detected_emotion = emotion
            fetch_all_recommendations.clear()
            st.rerun()

    # Fetch recommendations (parallel, cached 15 min)
    with st.spinner("Fetching recommendations from the internet..."):
        recs = fetch_all_recommendations(emotion)

    # Preload all poster/cover images so browser starts downloading immediately
    preload_tags = []
    for cat in ("books", "movies", "music", "games"):
        for item in recs.get(cat, [])[:8]:
            img = item.get("cover") or item.get("poster")
            if img:
                if "image.tmdb.org" in img:
                    img = img.replace("/w300/", "/w500/")
                preload_tags.append(
                    f'<link rel="preload" as="image" href="{img}">'
                )
    if preload_tags:
        st.markdown("\n".join(preload_tags), unsafe_allow_html=True)

    # Render each category
    _render_section("📚 Books",  "📚", recs.get("books", []),  "books")
    _render_section("🎬 Movies", "🎬", recs.get("movies", []), "movies")
    _render_section("🎵 Music",  "🎵", recs.get("music", []),  "music")
    _render_section("🎮 Games",  "🎮", recs.get("games", []),  "games")

    # Refresh button
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🔄 Refresh Recommendations", use_container_width=True,
                      key="rec_refresh_btn"):
            fetch_all_recommendations.clear()
            st.rerun()

    # Back to detection
    with col2:
        if st.button("📷 Back to Emotion Detection", use_container_width=True,
                      key="rec_back_btn"):
            st.session_state.sidebar_selected = "Emotion Detection"
            st.rerun()


if __name__ == "__main__":
    main()
