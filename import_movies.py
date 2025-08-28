import requests
from supabase import create_client

# === CONFIGURATION ===

SUPABASE_URL = "https://ifgsctyceaegqtbwiirh.supabase.co"        # <-- replace this
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlmZ3NjdHljZWFlZ3F0YndpaXJoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTEzMTMyMzYsImV4cCI6MjA2Njg4OTIzNn0.pn_orYXIM_SwhBKgY3SpYFeEXiew7Jqyg5gp7w4FIqY"                               # <-- replace this
TMDB_API_KEY = "b24e39d71bf2be74c414a5b79aded6c3"                           # <-- replace this

# === SETUP ===

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_tmdb_data(title):
    """Query TMDb for movie info by title."""
    search_url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title
    }

    response = requests.get(search_url, params=params)
    data = response.json()

    if data.get("results"):
        movie = data["results"][0]
        return {
            "tmdb_id": movie.get("id"),
            "title": movie.get("title"),
            "release_year": movie.get("release_date", "")[:4],
            "tmdb_rating": movie.get("vote_average"),
            "overview": movie.get("overview"),
            "poster_url": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get("poster_path") else None,
        }
    else:
        print(f"❌ No result found for: {title}")
        return None

def insert_into_supabase(movie_data):
    response = supabase.table("movies").insert(movie_data).execute()
    print(f"✅ Inserted: {movie_data['title']}")


# === MOVIE TITLES TO IMPORT ===

movie_titles = [
    "Barbie",
    "The Godfather",
    "Everything Everywhere All At Once",
    "Mad Max: Fury Road",
    "Hereditary"
]

# === MAIN EXECUTION ===

for title in movie_titles:
    movie_data = get_tmdb_data(title)
    if movie_data:
        insert_into_supabase(movie_data)
