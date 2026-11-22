"""Why each 2019 leak was or was not found (development aid)."""
import numpy as np

import detect
import network
import scoring

reps, evs = detect.run()
res = scoring.score(reps, 2019)
dist = detect.prepared()["L"].dist
pa = network.pipe_areas()
leaks = scoring.leak_table(2019)
ev19 = [e for e in evs if e["time"].year == 2019]
for lk in leaks:
    found = lk["link"] in res["detected"]
    s = lk["series"]
    peak = s.max()
    active = [e for e in ev19 if lk["start"] <= e["time"] <= lk["end"]]
    near = sorted(active, key=lambda e: dist.pipe(e["pipe"], lk["link"]))
    best = f"closest alarm {near[0]['pipe']} {dist.pipe(near[0]['pipe'], lk['link']):.0f} m" if near else "no alarm while active"
    print(f"{lk['link']:>5} {pa[lk['link']]} {lk['kind']:9s} {lk['start']:%Y-%m-%d}..{lk['end']:%m-%d} "
          f"peak {peak:5.1f} m3/h  {'FOUND' if found else 'missed':6s}  {best}")
