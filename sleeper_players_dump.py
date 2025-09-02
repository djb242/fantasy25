import requests, json, pandas as pd

URL = "https://api.sleeper.app/v1/players/nfl"
UA  = {"User-Agent": "Mozilla/5.0"}

def main():
    r = requests.get(URL, headers=UA, timeout=60)
    r.raise_for_status()
    data = r.json()  # dict keyed by player_id

    # RAW: full JSON dump (one big dict)
    with open("sleeper_players_raw.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # JSONL: one player per line (easier for some tools)
    with open("sleeper_players_raw.jsonl", "w", encoding="utf-8") as f:
        for pid, rec in data.items():
            row = {"player_id": pid, **(rec if isinstance(rec, dict) else {})}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # FLAT CSV: purely normalized fields (no derived values)
    values = []
    for pid, rec in data.items():
        if isinstance(rec, dict):
            values.append({"player_id": pid, **rec})
    if values:
        df = pd.json_normalize(values, sep=".")
        df.to_csv("sleeper_players_flat.csv", index=False)

    print("Wrote sleeper_players_raw.json, sleeper_players_raw.jsonl, sleeper_players_flat.csv")

if __name__ == "__main__":
    main()