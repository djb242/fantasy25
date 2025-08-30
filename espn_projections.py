# espn_projections.py
import asyncio
import json
import pandas as pd
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE_URL = "https://fantasy.espn.com/football/players/projections"
SEASON_ID = 2025         # season totals page
PAGE_SIZE = 50           # ESPN paginates UI by 50 (not critical here)

# Positions we care about
POS_MAP = {1:"QB", 2:"RB", 3:"WR", 4:"TE", 5:"K", 16:"DST"}

def pick_projection(stats, week=0):
    """Return ESPN’s own projection (no manual summing)."""
    want_split = 1 if week > 0 else 0
    for s in stats or []:
        if s.get("statSourceId") != 1:         # projections only
            continue
        if s.get("statSplitTypeId") != want_split:  # 0=season, 1=weekly
            continue
        if week > 0 and s.get("scoringPeriodId") != week:
            continue
        if s.get("appliedTotal") is not None:
            return float(s["appliedTotal"])
        if s.get("appliedAverage") is not None:
            return float(s["appliedAverage"])
    return None

def fetch_json(url, headers=None, timeout=60):
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8", errors="replace")
        return json.loads(data)

async def grab_players_json(page):
    """
    Navigate and capture the JSON XHR the page makes to ESPN's players API.
    """
    def is_players_api(resp):
        u = resp.url
        return ("/apis/v3/games/ffl" in u) and ("/players" in u) and ("view=" in u)

    # Minimal page initialization
    state = {}

    # Set up the waiter BEFORE navigating
    async with page.expect_response(is_players_api, timeout=120_000) as resp_info:
        await page.goto(f"{BASE_URL}?seasonId={SEASON_ID}",
                        wait_until="domcontentloaded", timeout=120_000)

    resp = await resp_info.value
    # Single rich fetch via direct HTTP
    try:
        xf = {
            "players": {
                "filterStatsForExternalIds": {"value": [2024, SEASON_ID]},
                "filterSlotIds": {"value": [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,23,24]},
                "filterStatsForSourceIds": {"value": [0,1]},
                "useFullProjectionTable": {"value": True},
                "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 3, "value": "102025"},
                "sortDraftRanks": {"sortPriority": 2, "sortAsc": True, "value": "PPR"},
                "sortPercOwned": {"sortPriority": 4, "sortAsc": False},
                "limit": 5000,
                "filterRanksForSlotIds": {"value": [0,2,4,6,17,16,8,9,10,12,13,24,11,14,15]},
                "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": ["002025","102025","002024","022025"]}
            }
        }
        league_url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON_ID}/segments/0/leaguedefaults/3?view=kona_player_info"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": BASE_URL,
            "x-fantasy-filter": json.dumps(xf, separators=(",", ":"))
        }
        data = fetch_json(league_url, headers=headers)
        try:
            print("Fetched league defaults players:", len(data.get("players", [])))
        except Exception:
            pass
        if isinstance(data, dict) and isinstance(data.get("players"), list) and data["players"]:
            return data
    except Exception as e:
        try:
            print("league defaults fetch error:", repr(e))
        except Exception:
            pass

    # Fallback: return whatever the original players request returned
    try:
        return await resp.json()
    except Exception:
        txt = await resp.text()
        return json.loads(txt)

def extract_rows(payload, week=0):
    """
    Handle payload being either a list of players or an object with 'players'.
    Only return (name, position, projected_points) for fantasy positions.
    """
    items = payload if isinstance(payload, list) else payload.get("players", [])
    out = []
    for item in items:
        p = item.get("player") if isinstance(item, dict) and "player" in item else item
        if not isinstance(p, dict):
            continue
        pos_id = p.get("defaultPositionId")
        if pos_id not in POS_MAP:
            continue
        stats_list = p.get("stats", [])
        pts = pick_projection(stats_list, week=week)
        if pts is None:
            continue
        name = p.get("fullName") or p.get("name") or ""
        out.append({"player_id": p.get("id"), "name": name, "position": POS_MAP[pos_id], "projected_points": pts})
    return out

async def main():
    # Use Playwright only to capture filter if needed, but our fetch uses direct HTTP
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))
        payload = await grab_players_json(page)
        await browser.close()

    # 2) Parse as season totals (week=0)
    rows = extract_rows(payload, week=0)

    # 3) De-dup and save
    seen = set()
    dedup = []
    for r in rows:
        pid = r.get("player_id")
        key = pid if pid is not None else (r["name"], r["position"]) 
        if key in seen: 
            continue
        seen.add(key)
        dedup.append(r)

    df = pd.DataFrame(dedup)
    if not df.empty:
        df.sort_values("projected_points", ascending=False, inplace=True, ignore_index=True)

    out = f"espn_projections_{SEASON_ID}_season.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"Saved {len(df)} players -> {out}")
    if not df.empty:
        print(df.head(15).to_string(index=False))

if __name__ == "__main__":
    asyncio.run(main())
