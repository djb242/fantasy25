#!/usr/bin/env python3
"""
draft_helper_step1.py

Minimal CLI draft helper.
- Loads a CSV of players with projected points.
- Lets you enter drafted players one by one (from any team).
- Recomputes the "best available" list after each entry.
- Purely sorts by projected points (Step 1). We'll add positional scarcity later.

USAGE:
    python draft_helper_step1.py --csv PATH/players.csv --top 15

EXPECTED COLUMNS (case-insensitive; flexible names allowed):
    - player name: one of ["player","name","full_name","fullName"]
    - position: one of ["pos","position"]
    - projected points: one of ["proj_points","projected","projected_points","points","fp","fpts"]

If your file uses different names, use --col-* overrides.
"""

import argparse
import sys
import pandas as pd
from difflib import get_close_matches

COL_PLAYER_CANDIDATES = ["player","name","full_name","fullName"]
COL_POS_CANDIDATES = ["pos","position"]
COL_POINTS_CANDIDATES = ["proj_points","projected","projected_points","points","fp","fpts"]

def normalize_columns(df):
    mapping = {}
    cols_lower = {c.lower(): c for c in df.columns}
    # player
    for k in COL_PLAYER_CANDIDATES:
        if k.lower() in cols_lower:
            mapping['player'] = cols_lower[k.lower()]
            break
    # position
    for k in COL_POS_CANDIDATES:
        if k.lower() in cols_lower:
            mapping['position'] = cols_lower[k.lower()]
            break
    # points
    for k in COL_POINTS_CANDIDATES:
        if k.lower() in cols_lower:
            mapping['proj_points'] = cols_lower[k.lower()]
            break
    missing = [k for k in ['player','position','proj_points'] if k not in mapping]
    if missing:
        raise ValueError(f"Could not auto-detect columns for: {missing}. "
                         f"Use --col-player/--col-pos/--col-points to specify manually.")
    return mapping

def load_data(args):
    df = pd.read_csv(args.csv)
    if args.col_player and args.col_player not in df.columns:
        raise ValueError(f"--col-player '{args.col_player}' not found in CSV columns: {list(df.columns)}")
    if args.col_pos and args.col_pos not in df.columns:
        raise ValueError(f"--col-pos '{args.col_pos}' not found in CSV columns: {list(df.columns)}")
    if args.col_points and args.col_points not in df.columns:
        raise ValueError(f"--col-points '{args.col_points}' not found in CSV columns: {list(df.columns)}")

    if args.col_player and args.col_pos and args.col_points:
        colmap = {'player': args.col_player, 'position': args.col_pos, 'proj_points': args.col_points}
    else:
        colmap = normalize_columns(df)

    # Rename to canonical
    df = df.rename(columns={
        colmap['player']: 'player',
        colmap['position']: 'position',
        colmap['proj_points']: 'proj_points'
    })
    # Clean types
    df['player'] = df['player'].astype(str).str.strip()
    df['position'] = df['position'].astype(str).str.upper().str.strip()
    # Coerce points to numeric
    df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
    df = df.dropna(subset=['proj_points'])
    # Remove duplicates on (player, position) keeping max proj_points
    df = df.sort_values('proj_points', ascending=False).drop_duplicates(subset=['player','position'], keep='first')
    df = df.reset_index(drop=True)
    return df

def show_top(df, drafted, topn):
    available = df[~df['player'].isin(drafted)].sort_values('proj_points', ascending=False)
    top = available.head(topn).copy()
    if top.empty:
        print("\nNo players left. Draft complete.")
        return False
    print("\nBest available (by projected points):")
    print(top[['player','position','proj_points']].to_string(index=False,
          formatters={'proj_points': lambda x: f'{x:.2f}'}))
    # also show best by position (top 3 each) for quick scanning
    print("\nBy position (top 3 each):")
    for pos, grp in available.groupby('position'):
        g = grp.head(3)[['player','proj_points']]
        if not g.empty:
            print(f"  {pos:>4}: " + ", ".join([f\"{r.player} ({r.proj_points:.1f})\" for r in g.itertuples()]))
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', required=True, help='Path to the players CSV')
    parser.add_argument('--top', type=int, default=15, help='How many players to display each update')
    parser.add_argument('--col-player', default=None, help='Override player column name')
    parser.add_argument('--col-pos', default=None, help='Override position column name')
    parser.add_argument('--col-points', default=None, help='Override projected points column name')
    args = parser.parse_args()

    try:
        df = load_data(args)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    all_names = df['player'].tolist()
    drafted = set()

    print(f"Loaded {len(df)} players from {args.csv}.")
    print("Enter drafted player names one per line. Type ':undo' to undo last draft, ':save PATH' to save remaining, ':quit' to exit.\n")

    history = []
    if not show_top(df, drafted, args.top):
        return

    while True:
        line = input("\nDrafted> ").strip()
        if not line:
            continue
        if line.lower() in (':q', ':quit', ':exit'):
            break
        if line.lower() == ':undo':
            if history:
                last = history.pop()
                drafted.remove(last)
                print(f"Undid: {last}")
                show_top(df, drafted, args.top)
            else:
                print("Nothing to undo.")
            continue
        if line.lower().startswith(':save'):
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                out = parts[1]
                remaining = df[~df['player'].isin(drafted)].copy()
                remaining.to_csv(out, index=False)
                print(f"Saved remaining player pool to {out}")
            else:
                print("Usage: :save /path/to/remaining.csv")
            continue

        # Try exact match first
        if line in drafted:
            print(f"Already drafted: {line}")
            continue
        if line in all_names:
            drafted.add(line)
            history.append(line)
            show_top(df, drafted, args.top)
            continue

        # Fuzzy match suggestion
        suggestion = get_close_matches(line, all_names, n=5, cutoff=0.6)
        if suggestion:
            print(f"Name not found. Did you mean one of: {', '.join(suggestion)} ?")
        else:
            print("Name not found. Try again (check spelling).")

if __name__ == '__main__':
    main()
