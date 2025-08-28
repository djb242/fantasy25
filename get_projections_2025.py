import time, requests, pandas as pd

BASE = "https://api.sleeper.app"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def compute_ppr(df: pd.DataFrame) -> pd.Series:
    def s(*names):
        for n in names:
            if n in df.columns:
                return pd.to_numeric(df[n], errors="coerce").fillna(0)
        return pd.Series(0, index=df.index, dtype="float64")
    return (
        s("pass_yd","passing_yards")/25
        + s("pass_td","passing_tds")*4
        - s("pass_int","interceptions")*2
        + s("rush_yd","rushing_yards")/10
        + s("rush_td","rushing_tds")*6
        + s("rec","receptions")*1
        + s("rec_yd","receiving_yards")/10
        + s("rec_td","receiving_tds")*6
        - s("fum_lost","fumbles_lost")*2
    )

def _normalize_rows(payload):
    """
    Sleeper projections may return a dict keyed by player_id or a list.
    Return a list of dicts with a 'player_id' column.
    """
    rows = []
    if isinstance(payload, dict):
        for pid, rec in payload.items():
            if isinstance(rec, dict):
                r = rec.copy()
                r.setdefault("player_id", pid)
                rows.append(r)
    elif isinstance(payload, list):
        for rec in payload:
            if isinstance(rec, dict):
                rows.append(rec.copy())
    return rows


def main():
    # Load your cached players table to attach names/pos/team
    players = pd.read_csv("sleeper_players.csv", dtype=str)

    all_rows = []
    for wk in range(1, 19):
        url = f"{BASE}/v1/projections/nfl/2025/regular/{wk}"
        payload = get_json(url)
        if not payload:
            continue

        rows = _normalize_rows(payload)   # <-- NEW
        for row in rows:
            row["week"] = wk
            row["season"] = 2025
            all_rows.append(row)
        time.sleep(0.2)

    dfw = pd.DataFrame(all_rows)
    if dfw.empty:
        raise SystemExit("No projections returned.")

    dfw["ppr_points_proj"] = compute_ppr(dfw)
    # Attach player meta
    out_weekly = dfw.merge(players[["player_id","full_name","position","team"]], on="player_id", how="left")
    out_season = (out_weekly.groupby("player_id", as_index=False)["ppr_points_proj"]
                  .sum().merge(players[["player_id","full_name","position","team"]], on="player_id", how="left"))
    out_season["season"] = 2025

    out_weekly.to_csv("projections_2025_weekly_ppr.csv", index=False)
    out_season.sort_values("ppr_points_proj", ascending=False).to_csv("projections_2025_season_totals_ppr.csv", index=False)
    print("Wrote projections_2025_weekly_ppr.csv and projections_2025_season_totals_ppr.csv")

if __name__ == "__main__":
    main()