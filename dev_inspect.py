import json, collections

path = 'espn_projections_2025.json'
d = json.load(open(path, 'r', encoding='utf-8'))

print('records:', len(d))

def apptotal(s):
    if s is None:
        return None
    if s.get('appliedTotal') is not None:
        return s['appliedTotal']
    ap = s.get('appliedStats')
    if isinstance(ap, dict):
        tot = 0.0; has=False
        for v in ap.values():
            if isinstance(v,(int,float)):
                tot += float(v); has=True
        if has:
            return tot
    return None

counts = collections.Counter()
with_pts = 0
missing = 0
for p in d:
    stats = p.get('stats') or []
    if not isinstance(stats, list):
        stats = []
    # season projections
    season = next((s for s in stats if s.get('scoringPeriodId')==0 and s.get('statSplitTypeId') in (0,'0',2,'2') and s.get('statSourceId') in (1,'1')), None)
    weekly = [s for s in stats if s.get('statSplitTypeId') in (1,'1') and s.get('statSourceId') in (1,'1') and (s.get('scoringPeriodId') or 0) >= 1]
    val = apptotal(season)
    if val is None and weekly:
        val = sum(apptotal(s) or 0.0 for s in weekly)
    if val is None:
        missing += 1
    else:
        with_pts += 1
    # track what season entry exists
    if season:
        key = (season.get('scoringPeriodId'), season.get('statSplitTypeId'), season.get('statSourceId'), 'has_applied' if season.get('appliedTotal') is not None else 'no_applied')
        counts[key]+=1
    else:
        counts[('no_season',None,None,None)] += 1

print('with_pts', with_pts, 'missing', missing)
for k,v in sorted(counts.items()):
    print(k, v)

