#!/usr/bin/env python3
"""
draft_helper_step2_vorp.py

Interactive fantasy draft helper using Value Over Replacement (VORP).
- Tracks drafted players (any team) and your own picks separately.
- Recomputes replacement levels by position as the league fills starters.
- Scores candidates by VORP adjusted for your roster needs (need > bench > blocked).

USAGE (example):
  python draft_helper_step2_vorp.py --csv "/path/to/espn_projections_2025_season.csv" \
    --teams 12 \
    --roster "QB:1,RB:2,WR:2,TE:1,FLEX:1,K:1,DST:1" \
    --bench  "QB:1,RB:1,WR:1,TE:0,K:0,DST:0" \
    --top 15

Type 'help' inside the program for commands.

COLUMN DETECTION (case-insensitive; auto-detects but you can override):
  --col-player  (default tries: player,name,full_name,fullName)
  --col-pos     (default tries: pos,position)
  --col-points  (default tries: proj_points,projected,projected_points,points,fp,fpts)

NOTES
- Positions in CSV are normalized (uppercased). Common aliases for defense are mapped to DST.
- FLEX is only a roster slot for your team capacity tracking; VORP is computed per base position.
- Replacement level for a position is the point value of the Nth remaining player at that position,
  where N = teams * starters_per_team[pos]. As the draft proceeds, N stays constant but we always
  look at the Nth remaining (i.e., re-evaluated as the pool shrinks).
- Need weighting:
    need_weight (default 1.0): you still have a starting slot to fill at that position (or a flex slot that can accept it).
    bench_weight (default 0.4): all your starters are filled but you have bench capacity.
    blocked_weight (default 0.1): no capacity left (starter+bench), still allow as depth.
"""

import argparse
import sys
import pandas as pd
from difflib import get_close_matches
from collections import defaultdict

COL_PLAYER_CANDIDATES = ["player","name","full_name","fullName"]
COL_POS_CANDIDATES = ["pos","position"]
COL_POINTS_CANDIDATES = ["proj_points","projected","projected_points","points","fp","fpts"]

DEF_ALIASES = {"DEF","DST","D/ST","D-ST","D\\ST","TEAM DEFENSE","TEAMDEF","TEAM D","DEFENSE"}

BASE_POSITIONS = ["QB","RB","WR","TE","K","DST"]  # FLEX is capacity only

def parse_kv_list(s, key_type=str, val_type=int):
    """
    Parse strings like "QB:1,RB:2,WR:2,TE:1,FLEX:1,K:1,DST:1"
    Returns dict {key_type(key): val_type(val)}
    """
    out = {}
    if not s:
        return out
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"Bad fragment '{part}' (expected KEY:VAL)")
        k,v = part.split(":",1)
        out[key_type(k.strip().upper())] = val_type(v.strip())
    return out

def normalize_columns(df):
    mapping = {}
    cols_lower = {c.lower(): c for c in df.columns}
    for k in COL_PLAYER_CANDIDATES:
        if k.lower() in cols_lower:
            mapping['player'] = cols_lower[k.lower()]
            break
    for k in COL_POS_CANDIDATES:
        if k.lower() in cols_lower:
            mapping['position'] = cols_lower[k.lower()]
            break
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
    # Column overrides sanity
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

    # Rename canonical
    df = df.rename(columns={
        colmap['player']: 'player',
        colmap['position']: 'position',
        colmap['proj_points']: 'proj_points'
    })
    # Clean
    df['player'] = df['player'].astype(str).str.strip()
    # normalize positions
    df['position'] = df['position'].astype(str).str.upper().str.strip()
    df['position'] = df['position'].replace({p:'DST' for p in DEF_ALIASES})
    # limit to known positions if present
    df = df[df['position'].isin(set(BASE_POSITIONS))].copy()
    # Coerce points numeric
    df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
    df = df.dropna(subset=['proj_points'])
    # De-dup on (player,position) keeping max
    df = df.sort_values('proj_points', ascending=False).drop_duplicates(subset=['player','position'], keep='first')
    df = df.reset_index(drop=True)
    return df

def compute_replacement_points(available_df, teams, starters_by_pos):
    """
    For each base position, find the Nth remaining player's proj_points as replacement,
    where N = teams * starters_by_pos[pos]. If fewer than N players remain, use the last one's points.
    Returns dict pos->replacement_points (float).
    """
    replacement = {}
    for pos in BASE_POSITIONS:
        N = teams * starters_by_pos.get(pos, 0)
        if N <= 0:
            # if no starters for this pos, set low replacement level to avoid picking
            replacement[pos] = float('inf')  # makes vorp negative, pushing it down
            continue
        pool = available_df[available_df['position'] == pos].sort_values('proj_points', ascending=False)
        if pool.empty:
            replacement[pos] = float('inf')
        else:
            # Nth remaining => zero-based index N-1
            idx = min(max(N-1, 0), len(pool)-1)
            replacement[pos] = float(pool.iloc[idx]['proj_points'])
    return replacement

def candidate_scores(available_df, replacement_points, my_needs, weights):
    """
    Compute VORP and adjust by my roster needs.
    my_needs: dict pos->state among {'need','bench','blocked'} giving how we should weight a position.
    weights: dict {'need':1.0, 'bench':0.4, 'blocked':0.1}
    Returns a new DataFrame with columns: player, position, proj_points, vorp, adj_score, need_state
    """
    rows = []
    for r in available_df.itertuples(index=False):
        pos = r.position
        repl = replacement_points.get(pos, float('inf'))
        vorp = r.proj_points - repl
        state = my_needs.get(pos, 'blocked')
        w = weights.get(state, 0.1)
        adj = vorp * w
        rows.append((r.player, pos, r.proj_points, vorp, adj, state))
    out = pd.DataFrame(rows, columns=['player','position','proj_points','vorp','adj_score','need_state'])
    return out.sort_values(['adj_score','vorp','proj_points'], ascending=[False, False, False]).reset_index(drop=True)

def compute_my_need_states(roster_slots, bench_slots, my_counts):
    """
    For each base position, classify as:
      - 'need' if starters not filled (or if FLEX can accept and starters filled elsewhere)
      - 'bench' if starters filled but bench slots available
      - 'blocked' otherwise
    Note: FLEX logic: if any FLEX slots > 0 and position in RB/WR/TE, treat as 'need' until FLEX filled.
    """
    states = {}
    # Count flex capacity consumed (we derive from my_counts['FLEX'])
    flex_accept = {'RB','WR','TE'}
    flex_total = roster_slots.get('FLEX', 0)
    flex_used = my_counts.get('FLEX', 0)
    flex_left = max(flex_total - flex_used, 0)

    for pos in BASE_POSITIONS:
        starters = roster_slots.get(pos, 0)
        bench = bench_slots.get(pos, 0)
        used = my_counts.get(pos, 0)

        # Determine starter need
        if used < starters:
            states[pos] = 'need'
            continue
        # FLEX can cover an extra starter-like slot for RB/WR/TE
        if pos in flex_accept and flex_left > 0:
            states[pos] = 'need'
            continue
        # Bench?
        if (used - starters) < bench:
            states[pos] = 'bench'
        else:
            states[pos] = 'blocked'
    return states

def printable_table(df, topn=15):
    if df.empty:
        return "No players left."
    show = df.head(topn).copy()
    show['proj_points'] = show['proj_points'].map(lambda x: f"{x:.2f}")
    show['vorp'] = show['vorp'].map(lambda x: f"{x:.2f}")
    show['adj_score'] = show['adj_score'].map(lambda x: f"{x:.3f}")
    return show[['player','position','proj_points','vorp','need_state','adj_score']].to_string(index=False)

def recalc_and_show(df_all, drafted, my_counts, teams, roster_slots, bench_slots, weights, topn):
    available = df_all[~df_all['player'].isin(drafted)].copy().sort_values('proj_points', ascending=False)
    if available.empty:
        print("\nDraft complete. No players left.")
        return False

    # compute replacement
    replacement_points = compute_replacement_points(available, teams, roster_slots)
    # compute my need states
    need_states = compute_my_need_states(roster_slots, bench_slots, my_counts)
    # compute scores
    scored = candidate_scores(available, replacement_points, need_states, weights)

    print("\nBest next picks (VORP-adjusted):")
    print(printable_table(scored, topn=topn))

    # also show replacement lines
    rp_out = []
    for p in BASE_POSITIONS:
        val = replacement_points[p]
        rp_out.append(f"{p}:{'N/A' if val==float('inf') else f'{val:.1f}'}")
    print("\nReplacement points by position: " + ", ".join(rp_out))

    # short position leaders (top 3)
    print("\nBy position (top 3 each by adj_score):")
    for pos in BASE_POSITIONS:
        posdf = scored[scored['position']==pos].head(3)
        if not posdf.empty:
            s = ", ".join([f"{r.player} ({r.proj_points:.1f}; VORP {r.vorp:.1f})" for r in posdf.itertuples()])
            print(f"  {pos:>4}: {s}")
    return True

HELP_TEXT = """
Commands:
  <name>           Mark player as drafted by the league (removes from pool)
  mine <name>      Mark player as YOUR pick (also updates your roster counts)
  undo             Undo the last action (drafted or mine)  [NOTE: currently only undoes league 'drafted']
  status           Show your roster fill and weights
  best             Re-show the current best list
  filter POS       Show top 10 for a specific position (e.g., "filter TE")
  save PATH        Save remaining pool with VORP scores to CSV at PATH
  help             Show this help
  quit             Exit

Tips:
- Names are matched exactly. If not found, you'll get close suggestions.
- Your roster capacity comes from --roster/--bench. FLEX accepts RB/WR/TE.
- Weights (need/bench/blocked) affect where depth is taken; tune with --weights.
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True, help='Path to players CSV')
    ap.add_argument('--teams', type=int, default=10, help='Number of teams in league (default 10)')
    ap.add_argument('--roster', default="QB:1,RB:2,WR:2,TE:1,FLEX:1,K:1,DST:1",
                    help='Starters per team, e.g., "QB:1,RB:2,WR:2,TE:1,FLEX:1,K:1,DST:1"')
    ap.add_argument('--bench', default="QB:0,RB:0,WR:0,TE:0,K:0,DST:0",
                    help='Bench capacity per position for YOUR team, e.g., "RB:2,WR:1"')
    ap.add_argument('--weights', default="need:1.0,bench:0.4,blocked:0.1",
                    help='Weights for need states, e.g., "need:1.0,bench:0.5,blocked:0.15"')
    ap.add_argument('--top', type=int, default=15, help='How many players to show each update')
    ap.add_argument('--col-player', default=None)
    ap.add_argument('--col-pos', default=None)
    ap.add_argument('--col-points', default=None)
    args = ap.parse_args()

    # Parse configs
    roster_slots = parse_kv_list(args.roster, key_type=str, val_type=int)
    bench_slots = parse_kv_list(args.bench, key_type=str, val_type=int)
    # parse weights
    w = {}
    for frag in args.weights.split(","):
        frag = frag.strip()
        if not frag: continue
        k,v = frag.split(":",1)
        w[k.strip().lower()] = float(v.strip())
    weights = {'need': w.get('need',1.0), 'bench': w.get('bench',0.4), 'blocked': w.get('blocked',0.1)}

    try:
        df = load_data(args)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    all_names = df['player'].tolist()
    drafted = []   # order-sensitive for undo
    drafted_set = set()
    my_counts = defaultdict(int)  # counts per position, plus 'FLEX' we increment when used

    print(f"Loaded {len(df)} players from {args.csv}. Teams={args.teams}. Roster={roster_slots}. Bench={bench_slots}.")
    print(HELP_TEXT.strip())

    if not recalc_and_show(df, drafted_set, my_counts, args.teams, roster_slots, bench_slots, weights, args.top):
        return

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not line:
            continue
        low = line.lower()

        if low in ('q','quit','exit'):
            break
        if low in ('h','help','?'):
            print(HELP_TEXT.strip())
            continue
        if low == 'best':
            recalc_and_show(df, drafted_set, my_counts, args.teams, roster_slots, bench_slots, weights, args.top)
            continue
        if low == 'status':
            print("Your roster used: " + ", ".join([f"{k}:{v}" for k,v in sorted(my_counts.items())]))
            print(f"Weights: {weights}")
            # show need states
            ns = compute_my_need_states(roster_slots, bench_slots, my_counts)
            print("Need states: " + ", ".join([f"{k}:{ns[k]}" for k in BASE_POSITIONS]))
            continue
        if low == 'undo':
            if not drafted:
                print("Nothing to undo.")
                continue
            act, name, pos = drafted.pop()
            if act == 'drafted':
                if name in drafted_set:
                    drafted_set.remove(name)
                print(f"Undid drafted: {name}")
            else:
                print("Undo for 'mine' not yet implemented.")
            continue
        if low.startswith('save '):
            path = line.split(None,1)[1]
            avail = df[~df['player'].isin(drafted_set)].copy()
            # compute scored table for saving
            replacement_points = compute_replacement_points(avail, args.teams, roster_slots)
            need_states = compute_my_need_states(roster_slots, bench_slots, my_counts)
            scored = candidate_scores(avail, replacement_points, need_states, weights)
            scored.to_csv(path, index=False)
            print(f"Saved remaining pool with scores to {path}")
            continue
        if low.startswith('filter '):
            pos = line.split(None,1)[1].strip().upper()
            if pos in DEF_ALIASES:
                pos = 'DST'
            if pos not in BASE_POSITIONS:
                print(f"Unknown position '{pos}'. Use one of {BASE_POSITIONS}.")
                continue
            avail = df[~df['player'].isin(drafted_set)].copy()
            replacement_points = compute_replacement_points(avail, args.teams, roster_slots)
            need_states = compute_my_need_states(roster_slots, bench_slots, my_counts)
            scored = candidate_scores(avail, replacement_points, need_states, weights)
            posdf = scored[scored['position']==pos].head(10)
            if posdf.empty:
                print(f"No players left at {pos}.")
            else:
                print(printable_table(posdf, topn=10))
            continue

        # "mine <name>"
        if low.startswith('mine '):
            name = line.split(None,1)[1].strip()
            # exact first
            if name not in all_names:
                suggestions = get_close_matches(name, all_names, n=5, cutoff=0.6)
                if suggestions:
                    print(f"Name not found. Did you mean: {', '.join(suggestions)} ?")
                    continue
                else:
                    print("Name not found. Check spelling.")
                    continue
            if name in drafted_set:
                print(f"Already drafted: {name}")
                continue
            # get pos
            pos = df[df['player']==name].iloc[0]['position']
            drafted.append(('mine', name, pos))
            drafted_set.add(name)
            # increment my roster counts: prefer filling starters; if starters full and FLEX available for RB/WR/TE, consume FLEX; else bench.
            pos_upper = pos.upper()
            flex_accept = {'RB','WR','TE'}
            starters = roster_slots.get(pos_upper, 0)
            if my_counts[pos_upper] < starters:
                my_counts[pos_upper] += 1
            elif pos_upper in flex_accept and my_counts.get('FLEX',0) < roster_slots.get('FLEX',0):
                my_counts['FLEX'] = my_counts.get('FLEX',0) + 1
            else:
                my_counts[pos_upper] += 1  # bench
            recalc_and_show(df, drafted_set, my_counts, args.teams, roster_slots, bench_slots, weights, args.top)
            continue

        # otherwise treat as league drafted name
        name = line.strip()
        if name not in all_names:
            suggestions = get_close_matches(name, all_names, n=5, cutoff=0.6)
            if suggestions:
                print(f"Name not found. Did you mean: {', '.join(suggestions)} ?")
                continue
            else:
                print("Name not found. Check spelling.")
                continue
        if name in drafted_set:
            print(f"Already drafted: {name}")
            continue
        pos = df[df['player']==name].iloc[0]['position']
        drafted.append(('drafted', name, pos))
        drafted_set.add(name)
        recalc_and_show(df, drafted_set, my_counts, args.teams, roster_slots, bench_slots, weights, args.top)

if __name__ == '__main__':
    main()
