import requests, pandas as pd
from io import BytesIO

URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/stats_player_week_2024.csv"

def main():
    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(BytesIO(r.content), low_memory=False)

    # Prefer built-in PPR column if present
    ppr_col = next((c for c in df.columns if c.lower() in ("fantasy_points_ppr","fantasy_points_p_p_r")), None)
    if ppr_col is None:
        # Fallback compute
        def g(names):
            for n in names:
                if n in df.columns:
                    return pd.to_numeric(df[n], errors="coerce").fillna(0)
            return pd.Series(0, index=df.index, dtype="float64")
        df["fantasy_points_ppr"] = (
            g(["passing_yards","pass_yds","pass_yards"])/25
            + g(["passing_tds","pass_td","pass_tds"])*4
            - g(["interceptions","pass_int"])*2
            + g(["rushing_yards","rush_yds","rush_yards"])/10
            + g(["rushing_tds","rush_td","rush_tds"])*6
            + g(["receptions","rec"])*1
            + g(["receiving_yards","rec_yds","rec_yards"])/10
            + g(["receiving_tds","rec_td","rec_tds"])*6
            - g(["fumbles_lost","fum_lost"])*2
        )
        ppr_col = "fantasy_points_ppr"

    name_col = "player_display_name" if "player_display_name" in df.columns else "player_name"
    id_col   = "player_id" if "player_id" in df.columns else ( "gsis_id" if "gsis_id" in df.columns else name_col )
    pos_col  = "position" if "position" in df.columns else None
    team_col = "recent_team" if "recent_team" in df.columns else ("team" if "team" in df.columns else None)

    totals = (df.groupby(id_col, as_index=False)[ppr_col].sum()
                .rename(columns={ppr_col: "ppr_points_total"}))
    attrs_cols = [c for c in [id_col, name_col, pos_col, team_col] if c]
    attrs = df[attrs_cols].drop_duplicates(subset=[id_col])
    out_totals = totals.merge(attrs, on=id_col, how="left")
    out_totals["season"] = 2024

    weekly = df[[id_col, name_col, "week"]].copy()
    weekly["ppr_points"] = df[ppr_col]
    if pos_col and pos_col in df: weekly["position"] = df[pos_col]
    if team_col and team_col in df: weekly["team"] = df[team_col]
    weekly["season"] = 2024

    # Standardize column names
    out_totals = out_totals.rename(columns={id_col:"player_id", name_col:"name"})
    weekly     = weekly.rename(columns={id_col:"player_id", name_col:"name"})

    out_totals.sort_values("ppr_points_total", ascending=False).to_csv("actuals_2024_season_totals_ppr.csv", index=False)
    weekly.sort_values(["week","ppr_points"], ascending=[True, False]).to_csv("actuals_2024_weekly_ppr.csv", index=False)
    print("Wrote actuals_2024_season_totals_ppr.csv and actuals_2024_weekly_ppr.csv")

if __name__ == "__main__":
    main()