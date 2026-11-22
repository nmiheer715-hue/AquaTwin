"""Export the L-Town network and AquaTwin's 2019 run into the control-room UI.

Reads ../dashboard/template.html, replaces /*__DATA__*/ with the data, and
writes ../dashboard/index.html (one self-contained file).
"""
import json
import os
from datetime import datetime

import numpy as np

import detect
import load
import network
import scoring

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, "..", "dashboard")


def main():
    wn = network.model()
    area = network.districts(wn)
    xy = {n: wn.get_node(n).coordinates for n in wn.node_name_list}
    xs = [p[0] for p in xy.values()]
    ys = [p[1] for p in xy.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W = 1000.0
    H = W * (y1 - y0) / (x1 - x0)

    def P(n):
        x, y = xy[n]
        return [round((x - x0) / (x1 - x0) * W, 1), round((y1 - y) / (y1 - y0) * H, 1)]

    paths = {"A": [], "B": [], "C": []}
    mids = {}
    for name, l in wn.links():
        a, b = P(l.start_node_name), P(l.end_node_name)
        paths[area.get(l.start_node_name, "A")].append(f"M{a[0]} {a[1]}L{b[0]} {b[1]}")
        mids[name] = [round((a[0] + b[0]) / 2, 1), round((a[1] + b[1]) / 2, 1)]

    d = load.load()
    sensors = [dict(id=s, p=P(s), area=area[s]) for s in d["pressures_cols"]]
    amr = [P(s) for s in d["demands_cols"]]

    reps, evs = detect.run()
    res = scoring.score(reps, 2019)
    ev_by = {(e["pipe"], e["time"]): e for e in evs}
    day0 = datetime(2019, 1, 1)
    L = detect.prepared()["L"]
    leak_tab = scoring.leak_table(2019)
    alarms = []
    for r in res["rows"]:
        e = ev_by.get((r["link"], r["time"]))
        status = "hit" if r["hit"] and r["hit"] != "repeat" else ("repeat" if r["hit"] else "false")
        zone_leak = None
        if status == "false" and e:
            for lk in leak_tab:
                if lk["start"] <= r["time"] <= lk["end"] and any(L.dist.pipe_node(lk["link"], n) <= 300 for n in e["top"]):
                    zone_leak = lk["link"]
                    break
        alarms.append(dict(
            t=r["time"].strftime("%Y-%m-%d %H:%M"), day=(r["time"] - day0).days,
            pipe=r["link"], at=mids[r["link"]],
            zone=(e["zone"] if e else "carry"), size=(e["size_m3h"] if e else None),
            top=[P(n) for n in (e["top"] if e else [])], status=status, leak=r["hit"] if status == "hit" else None,
            nearest=r["nearest_leak"], dist=r["nearest_m"], eur=r["score"], zone_leak=zone_leak))

    leaks = []
    for lk in scoring.leak_table(2019):
        s = max(0, (lk["start"] - day0).days)
        leaks.append(dict(pipe=lk["link"], at=mids[lk["link"]], start=s, end=min(364, (lk["end"] - day0).days),
                          kind=lk["kind"], area=network.pipe_areas(wn)[lk["link"]],
                          found=lk["link"] in res["detected"],
                          peak=round(float(lk["series"].max()), 2)))

    P_ = detect.prepared()
    ab = P_["ind"]["AB"][365:730]
    c = P_["ind"]["C"][365:730]
    data = dict(
        W=W, H=round(H, 1), paths={k: "".join(v) for k, v in paths.items()},
        sensors=sensors, amr=amr,
        tanks={n: P(n) for n in ("R1", "R2", "T1")},
        alarms=alarms, leaks=leaks,
        series=dict(ab=[round(float(v), 2) for v in ab], c=[round(float(v), 3) for v in c]),
        thr=dict(ab=detect.CFG["thr_ab"], c=detect.CFG["thr_c"]),
        score=dict(total=res["total"], tp=res["tp"], fp=res["fp"], n=res["n_leaks"], perfect=523153.82,
                   zone=json.load(open(os.path.join(HERE, "results", "battledim_score.json")))["evaluation_2019"]["zone_found"]),
    )
    tpl = open(os.path.join(DASH, "template.html"), encoding="utf-8").read()
    out = tpl.replace("/*__DATA__*/", "const DATA = " + json.dumps(data, separators=(",", ":")) + ";")
    # artifact.html: page body only (the publishing host adds the document wrapper)
    open(os.path.join(DASH, "artifact.html"), "w", encoding="utf-8").write(out)
    # index.html: complete document for opening locally / screen recording
    full = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<style>html,body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
            + out.replace("<style>", "</head><body><style>", 1) if False else
            '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + out + "\n</html>")
    full = full.replace("<style>", "<style>html,body{margin:0}[hidden]{display:none!important}\n", 1)
    open(os.path.join(DASH, "index.html"), "w", encoding="utf-8").write(full)
    print(f"wrote dashboard/index.html + artifact.html  ({len(out) / 1024:.0f} KB, {len(alarms)} alarms, {len(leaks)} leaks)")


if __name__ == "__main__":
    main()
