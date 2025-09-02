import sys, json, pandas as pd, io

USAGE = "python convert_json_to_csv.py <input.json> <output.csv> [season]"

def load_any(path):
    # Try JSON array/object first
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    try:
        data = json.loads(txt)
        # Some responses may be {"players":[...]} – normalize
        if isinstance(data, dict) and "players" in data and isinstance(data["players"], list):
            return data["players"]
        return data
    except Exception:
        # Fallback: NDJSON (one JSON per line)
        rows = []
        for line in io.StringIO(txt):
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

def pick_season_projection(stats):
    """
    Return the stats dict representing SEASON projections.
    ESPN commonly uses scoringPeriodId==0, statSplitTypeId==0, statSourceId==1.
    If absent, caller should sum weekly projections (splitTypeId==1, sourceId==1).
    """
    if not isinstance(stats, list):
        return None
    # Primary: season aggregate projections
    for s in stats:
        if (
            s.get("scoringPeriodId") == 0
            and s.get("statSplitTypeId") in (0, "0")
            and s.get("statSourceId") in (1, "1")
        ):
            return s
    # Back-compat: rare feeds may use splitTypeId 2
    for s in stats:
        if (
            s.get("scoringPeriodId") == 0
            and s.get("statSplitTypeId") in (2, "2")
            and s.get("statSourceId") in (1, "1")
        ):
            return s
    # Last resort season actuals (sourceId 0)
    for s in stats:
        if (
            s.get("scoringPeriodId") == 0
            and s.get("statSplitTypeId") in (0, 2, "0", "2")
            and s.get("statSourceId") in (0, "0")
        ):
            return s
    return None

def get_applied_points(sp):
    """
    Prefer ESPN's appliedTotal if present; otherwise sum appliedStats values.
    This does NOT re-score; it uses ESPN-applied per-stat points.
    """
    if sp is None:
        return None
    if "appliedTotal" in sp and sp["appliedTotal"] is not None:
        return sp["appliedTotal"]
    applied = sp.get("appliedStats") or {}
    if isinstance(applied, dict):
        total = 0.0
        has_num = False
        for v in applied.values():
            if isinstance(v, (int, float)):
                total += float(v)
                has_num = True
        if has_num:
            return total
    return None

def main():
    if len(sys.argv) < 3:
        print(USAGE); sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]
    season = int(sys.argv[3]) if len(sys.argv) > 3 else 2025

    data = load_any(in_path)
    if not isinstance(data, list):
        print("Input is not a JSON array of players.", file=sys.stderr); sys.exit(2)

    rows = []
    for p in data:
        if not isinstance(p, dict): 
            continue
        stats = p.get("stats", [])
        sp = pick_season_projection(stats)
        pts = get_applied_points(sp)
        # Fallback: sum weekly projections if season aggregate missing
        if pts is None and isinstance(stats, list):
            # Prefer weekly projections, otherwise weekly actuals
            weekly = [
                s for s in stats
                if s.get("statSplitTypeId") in (1, "1")
                and s.get("statSourceId") in (1, "1")
                and (s.get("scoringPeriodId") or 0) >= 1
            ]
            if not weekly:
                weekly = [
                    s for s in stats
                    if s.get("statSplitTypeId") in (1, "1")
                    and s.get("statSourceId") in (0, "0")
                    and (s.get("scoringPeriodId") or 0) >= 1
                ]
            if weekly:
                total = 0.0
                for s in weekly:
                    ap = get_applied_points(s)
                    if ap is not None:
                        total += float(ap)
                pts = total
        rows.append({
            "player_id": p.get("id"),
            "name": p.get("fullName"),
            "position_id": p.get("defaultPositionId"),
            "team_id": p.get("proTeamId"),
            "season": season,
            "proj_points": pts
        })

    df = pd.DataFrame(rows)
    # Keep rows even if proj_points is NaN so you can inspect what’s missing
    df.to_csv(out_path, index=False)
    print(f"Wrote {out_path} with {len(df)} rows; "
          f"{df['proj_points'].notna().sum()} have proj_points.")

if __name__ == "__main__":
    main()
