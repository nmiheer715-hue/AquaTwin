"""Parameter selection on the 2018 development year only.

Part A  validates the year-end leak pursuit at month ends in 2018: how many
        leaks active on that date it hits (within 300 m), and how many
        reports miss.
Part B  coordinate sweep of the detection/localisation settings, selected by
        the 2018 economic score (official rules). 2019 is printed only so the
        held-out result can be reported; it is never used for selection.

Usage:  python sweep.py A | B
"""
import itertools
import json
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np

import detect
import scoring

HERE = os.path.dirname(os.path.abspath(__file__))


def score_both(cfg):
    reps, evs = detect.run(cfg)
    r18 = scoring.score([(e["pipe"], e["time"]) for e in evs if e["time"].year == 2018 and not e["growth"]],
                        2018, dist=detect.prepared()["L"].dist)
    r19 = scoring.score(reps, 2019, dist=detect.prepared()["L"].dist)
    return r18, r19


def part_a():
    P = detect.prepared()
    ind, pn, L = P["ind"], P["pn"], P["L"]
    leaks = scoring.leak_table(2018)
    thr = {"AB": detect.CFG["thr_ab"], "C": detect.CFG["thr_c"]}
    dates = [datetime(2018, m, 1) - timedelta(days=1) for m in range(4, 13)] + [datetime(2018, 12, 31)]
    best = None
    for nights, qmin in itertools.product((3, 7, 14), (1.0, 1.5, 2.0, 3.0)):
        hits = fps = 0
        for dt in dates:
            k = (dt - datetime(2018, 1, 1)).days
            active = [l for l in leaks if l["start"] <= dt <= l["end"]]
            found = set()
            for z in ("AB", "C"):
                ex = float(np.median(ind[z][k - nights + 1:k + 1]) - np.median(ind[z][:7]))
                dp = pn[k - nights + 1:k + 1].mean(0) - pn[:7].mean(0)
                for pipe, _ in detect.pursuit(L, dp, z, ex, thr[z], q_min=qmin * thr[z]):
                    near = [l["link"] for l in active if L.dist.pipe(pipe, l["link"]) <= 300]
                    new = [x for x in near if x not in found]
                    if new:
                        found.add(new[0]); hits += 1
                    elif not near:
                        fps += 1
        n_act = sum(len([l for l in leaks if l["start"] <= dt <= l["end"]]) for dt in dates)
        print(f"nights {nights:2d} qmin {qmin:.1f}: hits {hits}/{n_act}  misses {fps}")
        key = hits - 0.25 * fps
        if best is None or key > best[0]:
            best = (key, nights, qmin)
    print("selected (2018 only): nights", best[1], "qmin", best[2])
    return best[1], best[2]


def part_b():
    grid = dict(nights=(1, 2, 3), same_m=(0.0, 150.0, 300.0), topk=(4, 8, 12), tau=(0.1, 0.25, 0.5),
                thr_ab=(2.0, 2.5, 3.5), thr_c=(0.5, 0.8, 1.2), big=(2.0, 3.0, 4.0))
    cfg = dict(detect.CFG)
    log = []
    for sweep_round in range(2):
        for key, vals in grid.items():
            results = []
            for v in vals:
                c = {**cfg, key: v}
                t0 = time.time()
                r18, r19 = score_both(c)
                results.append((r18["total"], v, r18, r19))
                log.append(dict(round=sweep_round, key=key, value=v, s18=r18["total"], tp18=r18["tp"],
                                fp18=r18["fp"], s19=r19["total"], tp19=r19["tp"], fp19=r19["fp"]))
                print(f"r{sweep_round} {key:7s}={v!s:6s} 2018 EUR {r18['total']:>9,.0f} TP {r18['tp']:2d} FP {r18['fp']:2d}"
                      f"   | 2019 EUR {r19['total']:>9,.0f} TP {r19['tp']:2d} FP {r19['fp']:2d}  ({time.time() - t0:.0f}s)",
                      flush=True)
            cfg[key] = max(results, key=lambda r: r[0])[1]
        print("config after round", sweep_round, {k: cfg[k] for k in grid})
    json.dump(dict(selected=cfg, log=log), open(os.path.join(HERE, "results", "sweep.json"), "w"), indent=1)
    return cfg


SIGMA_AB, SIGMA_C = 1.056, 0.132     # measured 2018 daily noise (m3/h)
FP_COST_UTILITY = 2500.0             # realistic cost of a crew + dig on a false alarm (EUR)


def part_c():
    """Low-false-alarm operating point. Objective (fixed before running):
    2018 official score, but each false alarm charged EUR 2,500."""
    best, log = None, []
    for ks, dm, cq in itertools.product((2.5, 3.0, 3.5, 4.0), (0.0, 100.0, 200.0, 300.0), (1.5, 2.0, 3.0)):
        cfg = dict(detect.CFG, thr_ab=ks * SIGMA_AB, thr_c=ks * SIGMA_C, dedupe_m=dm, carry_qmin=cq)
        r18, r19 = score_both(cfg)
        obj = r18["total"] - (FP_COST_UTILITY - 500.0) * r18["fp"]
        log.append(dict(k_sigma=ks, dedupe_m=dm, carry_qmin=cq, obj18=obj, s18=r18["total"], tp18=r18["tp"],
                        fp18=r18["fp"], s19=r19["total"], tp19=r19["tp"], fp19=r19["fp"]))
        print(f"k {ks:.1f}σ dedupe {dm:5.0f} m carry {cq:.1f} | 2018 obj {obj:>9,.0f} TP {r18['tp']:2d} FP {r18['fp']:2d}"
              f" | 2019 EUR {r19['total']:>9,.0f} TP {r19['tp']:2d} FP {r19['fp']:2d}", flush=True)
        if best is None or obj > best[0]:
            best = (obj, ks, dm, cq)
    print("SELECTED on 2018 (low-alarm):", dict(k_sigma=best[1], dedupe_m=best[2], carry_qmin=best[3]))
    json.dump(dict(selected=dict(k_sigma=best[1], dedupe_m=best[2], carry_qmin=best[3]), log=log),
              open(os.path.join(HERE, "results", "sweep_lowfp.json"), "w"), indent=1)


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    {"A": part_a, "B": part_b, "C": part_c}[sys.argv[1] if len(sys.argv) > 1 else "B"]()
