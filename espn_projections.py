# espn_projections.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright

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

async def grab_players_json(page):
    """
    Navigate and capture the JSON XHR the page makes to ESPN's players API.
    """
    def is_players_api(resp):
        u = resp.url
        return ("/apis/v3/games/ffl" in u) and ("/players" in u) and ("view=" in u)

    # Set up the waiter BEFORE navigating
    async with page.expect_response(is_players_api, timeout=120_000) as resp_info:
        await page.goto(f"{BASE_URL}?seasonId={SEASON_ID}",
                        wait_until="domcontentloaded", timeout=120_000)

    resp = await resp_info.value

    # Try json(); fall back to text -> json
    try:
        return await resp.json()
    except Exception:
        txt = await resp.text()
        import json
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
        pts = pick_projection(p.get("stats", []), week=week)
        if pts is None:
            continue
        name = p.get("fullName") or p.get("name") or ""
        out.append({"name": name, "position": POS_MAP[pos_id], "projected_points": pts})
    return out

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ))

        # 1) Capture the JSON the page uses
        payload = await grab_players_json(page)
        print("DEBUG type:", type(payload), "top keys:", list(payload.keys())[:10] if isinstance(payload, dict) else "list")
        sample = payload[0] if isinstance(payload, list) and payload else (payload.get("players", [{}])[0] if isinstance(payload, dict) else {})
        print("DEBUG sample keys:", list(sample.keys()))

        await browser.close()

    # 2) Parse as season totals (week=0)
    rows = extract_rows(payload, week=0)

    # 3) De-dup and save
    seen = set()
    dedup = []
    for r in rows:
        key = (r["name"], r["position"])
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