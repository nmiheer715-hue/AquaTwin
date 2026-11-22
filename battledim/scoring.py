"""Python port of the official BattLeDIM 2020 scoring algorithm
(KIOS-Research/BattLeDIM, Scoring Algorithm/Scoring_Algorithm.m and
functions/scoring_function.m). Same rules:

  - a detection is (pipe ID, time). It is successful for a leak if the time
    is within the leak's start..end and the centre-to-centre pipe distance
    is <= 300 m.
  - score of a successful detection = water saved from detection to the end
    of the year (EUR 0.80 per m3) - crew cost (EUR 500 x distance / 300 m).
  - an unsuccessful detection costs EUR 500 (false positive).
  - a repeated detection of an already detected leak scores 0.
  - detections dated in the previous year are ignored.

Also scores 2018 the same way, for development (the official scorer only
covers 2019).
"""
import os
from datetime import datetime

import numpy as np

import load
import network

HERE = os.path.dirname(os.path.abspath(__file__))
XMAX, COST_WATER, COST_CREW = 300.0, 0.80, 500.0


def steps(ts, year):
    t0 = datetime(year, 1, 1)
    return int(round((ts - t0).total_seconds() / 300.0))


def leak_table(year):
    """Leaks active in `year` from the dataset configuration, with their
    m3/h series for that year from the answer key."""
    d = load.load()
    cfg = open(os.path.join(HERE, "raw", "dataset_configuration.yaml")).read().splitlines()
    rows = []
    for line in cfg:
        line = line.strip()
        if line.startswith("- p") and line.count(",") >= 5:
            f = [x.strip() for x in line[2:].split(",")]
            rows.append(dict(link=f[0], start=datetime.strptime(f[1], "%Y-%m-%d %H:%M"),
                             end=datetime.strptime(f[2], "%Y-%m-%d %H:%M"), diam=float(f[3]), kind=f[4]))
    cols = list(d[f"leaks_cols_{year}"])
    L = d[f"leaks_{year}"]
    out = []
    for r in rows:
        if r["link"] in cols and r["start"].year <= year and r["end"].year >= year:
            r = dict(r)
            r["series"] = L[:, cols.index(r["link"])].astype(np.float64)
            r["t0"], r["t1"] = steps(r["start"], year), steps(r["end"], year)
            out.append(r)
    return out


def score(detections, year=2019, dist=None, verbose=False):
    """detections: list of (link_id, datetime). Returns a result dict."""
    dist = dist or network.Distances()
    leaks = leak_table(year)
    dets = sorted([(l, steps(t, year), t) for l, t in detections if steps(t, year) >= 0], key=lambda x: x[1])
    detected, total, fp, rows = [], 0.0, 0, []
    for link, td, t in dets:
        succ, sc, xs = [], {}, {}
        for j, lk in enumerate(leaks):
            x = dist.pipe(link, lk["link"])
            xs[j] = x
            if lk["t0"] <= td <= lk["t1"] and abs(x) <= XMAX:
                tdi = max(td, 1)
                saved = lk["series"][tdi - 1:].sum() / 12.0
                sc[j] = saved * COST_WATER - (x / XMAX) * COST_CREW
                succ.append(j)
        if succ:
            new = [j for j in succ if j not in detected]
            if not new:
                s, hit = 0.0, "repeat"
            else:
                j = min(new, key=lambda k: xs[k])
                detected.append(j)
                s, hit = sc[j], leaks[j]["link"]
        else:
            fp += 1
            s, hit = -COST_CREW, None
        total += s
        rows.append(dict(link=link, time=t, hit=hit, score=round(s, 2),
                         nearest_leak=leaks[min(xs, key=xs.get)]["link"] if xs else None,
                         nearest_m=round(min(xs.values()), 1) if xs else None))
        if verbose:
            print(f"{t:%Y-%m-%d %H:%M}  {link:>6}  -> {hit or 'FALSE POSITIVE':>14}  {s:>10.2f}")
    tp = len(detected)
    return dict(total=round(total, 2), tp=tp, fp=fp, fn=len(leaks) - tp, n_leaks=len(leaks),
                tpr=tp / len(leaks), rows=rows, detected=[leaks[j]["link"] for j in detected])


def zone_found(events, year=2019, dist=None, xmax=XMAX):
    """Leaks inside an alarm's search zone: within xmax of any candidate node
    the alarm showed, while the leak was running. This is not part of the
    official score; it measures what a crew searching the zone would reach.
    events: dicts with 'time', 'pipe', 'top' (candidate node IDs)."""
    dist = dist or network.Distances()
    out = []
    for lk in leak_table(year):
        for e in events:
            if not (lk["start"] <= e["time"] <= lk["end"]):
                continue
            nodes = list(e.get("top") or [])
            if dist.pipe(e["pipe"], lk["link"]) <= xmax or any(dist.pipe_node(lk["link"], n) <= xmax for n in nodes):
                out.append(lk["link"])
                break
    return out


def perfect(year=2019):
    """Every leak reported on its own pipe at its start (or 00:05 if it
    started in an earlier year): the official PERFECT_TEAM file."""
    dets = []
    for lk in leak_table(year):
        t = lk["start"] if lk["start"].year == year else datetime(year, 1, 1, 0, 5)
        dets.append((lk["link"], t))
    return dets


if __name__ == "__main__":
    r = score(perfect(2019))
    print(f"PERFECT 2019: EUR {r['total']:,.2f}  (official report: EUR 523,153.82)  TP {r['tp']}/{r['n_leaks']}")
    r = score(perfect(2018), 2018)
    print(f"PERFECT 2018: EUR {r['total']:,.2f}  TP {r['tp']}/{r['n_leaks']}")
