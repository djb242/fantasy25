import requests
import pandas as pd

URL = "https://api.sleeper.app/v1/players/nfl"  # Sleeper docs: players endpoint

def main():
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    data = r.json()  # dict keyed by player_id

    rows = []
    for pid, p in data.items():
        rows.append({
            "player_id": pid,
            "full_name": p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
            "first_name": p.get("first_name"),
            "last_name": p.get("last_name"),
            "position": p.get("position"),
            "fantasy_positions": ",".join(p.get("fantasy_positions", []) or []),
            "team": p.get("team"),
            "status": p.get("status"),
            "age": p.get("age"),
            "height": p.get("height"),
            "weight": p.get("weight"),
            "espn_id": p.get("espn_id"),
            "yahoo_id": p.get("yahoo_id"),
            "sportradar_id": p.get("sportradar_id"),
            "rotowire_id": p.get("rotowire_id"),
            "rotoworld_id": p.get("rotoworld_id"),
        })

    df = pd.DataFrame(rows)
    df.to_csv("sleeper_players.csv", index=False)
    print("Wrote sleeper_players.csv with", len(df), "rows")

if __name__ == "__main__":
    main()