import requests
from pathlib import Path

URL  = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/stats_player_week_2024.csv"
DEST = Path("nflverse_player_week_2024.csv")  # saved exactly as published

def main():
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
    r.raise_for_status()
    DEST.write_bytes(r.content)
    print(f"Wrote {DEST} (unchanged from source)")

if __name__ == "__main__":
    main()
