import time, json, requests, pandas as pd

BASE = "https://api.sleeper.app"
UA   = {"User-Agent": "Mozilla/5.0"}

SEASON = 2025
WEEKS  = range(1, 19)          # edit if needed
SEASON_TYPE = "regular"        # or "post"

def _rows(payload):
    # Normalize to list[dict] and add player_id if payload is dict
    if isinstance(payload, dict):
        return [{"player_id": pid, **rec} for pid, rec in payload.items() if isinstance(rec, dict)]
    if isinstance(payload, list):
        return [rec for rec in payload if isinstance(rec, dict)]
    return []

def main():
    all_rows = []
    with open(f"sleeper_projections_{SEASON}_{SEASON_TYPE}_raw.jsonl", "w", encoding="utf-8") as out_raw:
        for wk in WEEKS:
            url = f"{BASE}/v1/projections/nfl/{SEASON}/{SEASON_TYPE}/{wk}"
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            payload = r.json()

            rows = _rows(payload)
            for rec in rows:
                rec["season"] = SEASON
                rec["week"] = wk
                # RAW JSONL (preserves nested 'stats' exactly as provided)
                out_raw.write(json.dumps(rec, ensure_ascii=False) + "\n")
                all_rows.append(rec)
            time.sleep(0.2)

    # FLAT CSV (still only original fields; stats.* columns come from the nested 'stats' dict)
    if all_rows:
        df = pd.json_normalize(all_rows, sep=".")
        df.to_csv(f"sleeper_projections_{SEASON}_{SEASON_TYPE}_flat.csv", index=False)

    print(f"Wrote sleeper_projections_{SEASON}_{SEASON_TYPE}_raw.jsonl and sleeper_projections_{SEASON}_{SEASON_TYPE}_flat.csv")

if __name__ == "__main__":
    main()