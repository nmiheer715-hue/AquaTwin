"""Smart pressure management: lower PRV settings when demand allows.

For every pressure-reducing valve (PRV) the area it feeds is found (the
network cut at valves and pumps). For each hour of a typical day the twin
finds how far the PRVs feeding an area can be turned down while every
customer junction stays at or above the minimum service pressure plus a
safety margin. PRVs feeding the same area move together. Areas downstream of
another PRV area are solved after it.

Leakage saving uses FAVAD (Fixed And Variable Area Discharge): leak flow is
proportional to pressure^N1. N1 = 1.0 is the usual planning value for mixed
pipe materials (0.5 for rigid metal, 1.5 for plastic).

    python -m aquatwin.pressure network.inp [--min 17] [--margin 2] [--out DIR]
"""
import argparse
import json
import os

import networkx as nx
import numpy as np
import wntr

MIN_SERVICE_M = 17.0      # CPHEEO: minimum residual pressure for 3-storey buildings
MARGIN_M = 2.0            # model uncertainty margin
N1 = 1.0
HOURS = list(range(24))


def prv_areas(wn):
    G = nx.Graph()
    for n in wn.node_name_list:
        G.add_node(n)
    for name, l in wn.links():
        if l.link_type == "Pipe":
            G.add_edge(l.start_node_name, l.end_node_name)
    comp_of = {}
    for i, c in enumerate(nx.connected_components(G)):
        for n in c:
            comp_of[n] = i
    comps = {i: set() for i in set(comp_of.values())}
    for n, i in comp_of.items():
        comps[i].add(n)
    areas = {}
    for name, v in wn.valves():
        if v.valve_type != "PRV":
            continue
        c = comp_of[v.end_node_name]
        a = areas.setdefault(c, dict(prvs=[], nodes=comps[c], upstream=set()))
        a["prvs"].append(name)
        a["upstream"].add(comp_of[v.start_node_name])
    # order: areas fed from other PRV areas come after them
    order, done = [], set()
    while len(order) < len(areas):
        for c, a in areas.items():
            if c in done:
                continue
            if all(u not in areas or u in done or u == c for u in a["upstream"]):
                order.append(c)
                done.add(c)
    return [dict(id=f"PRV area {k + 1}", comp=c, **areas[c]) for k, c in enumerate(order)]


def snapshot(inp, hour, deltas, prv_base, tag="p"):
    wn = wntr.network.WaterNetworkModel(inp)
    wn.options.time.duration = 0
    wn.options.time.pattern_start = int(hour * 3600)
    for prv, d in deltas.items():
        wn.get_link(prv).initial_setting = max(1.0, prv_base[prv] - d)
    prefix = os.path.join(os.environ.get("TEMP", "."), f"aqpm_{os.getpid()}_{tag}")
    r = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=prefix)
    return r.node["pressure"].iloc[0]


def optimise(inp, min_service=MIN_SERVICE_M, margin=MARGIN_M, progress=print):
    wn = wntr.network.WaterNetworkModel(inp)
    areas = prv_areas(wn)
    if not areas:
        return dict(areas=[], note="no PRVs in this network: pressure management needs PRVs or variable-speed pumps")
    prv_base = {p: float(wn.get_link(p).initial_setting) for a in areas for p in a["prvs"]}
    demand = {n: sum(max(0, d.base_value) for d in wn.get_node(n).demand_timeseries_list) for n in wn.junction_name_list}
    customers = {a["id"]: [n for n in a["nodes"] if demand.get(n, 0) > 0] for a in areas}
    floor = min_service + margin
    schedule = {a["id"]: [0.0] * 24 for a in areas}
    before, after = {}, {}
    for h in HOURS:
        p0 = snapshot(inp, h, {}, prv_base, "b")
        before[h] = p0
        deltas = {}
        for a in areas:
            nodes = [n for n in customers[a["id"]] if p0[n] >= floor]     # junctions already below the floor are left out
            if not nodes:
                continue
            hi = min(prv_base[p] for p in a["prvs"]) - 5.0
            lo = 0.0
            while hi - lo > 0.5:                                          # binary search on the setting reduction
                mid = (lo + hi) / 2
                trial = {**deltas, **{p: mid for p in a["prvs"]}}
                pr = snapshot(inp, h, trial, prv_base, "s")
                ok = all(pr[n] >= floor for n in nodes) and all(pr[n] >= floor for b in areas
                                                                 for n in customers[b["id"]] if n in deltas and False)
                lo, hi = (mid, hi) if ok else (lo, mid)
            for p in a["prvs"]:
                deltas[p] = round(lo, 1)
            schedule[a["id"]][h] = round(lo, 1)
        after[h] = snapshot(inp, h, deltas, prv_base, "a")
        progress(f"  {h:02d}:00  PRV reduction " + ", ".join(f"{a['id']}: {schedule[a['id']][h]:.1f} m" for a in areas))

    rows = []
    for a in areas:
        nodes = customers[a["id"]]
        P0 = np.array([[before[h][n] for n in nodes] for h in HOURS])
        P1 = np.array([[after[h][n] for n in nodes] for h in HOURS])
        ok = P0 > 0
        ratio = np.where(ok, np.clip(P1, 0, None) / np.where(ok, P0, 1), 1.0)
        below0 = int((P0.min(0) < floor).sum())
        rows.append(dict(id=a["id"], prvs=a["prvs"], junctions=len(nodes),
                         settings_m={p: prv_base[p] for p in a["prvs"]},
                         schedule_reduction_m=schedule[a["id"]],
                         mean_pressure_before_m=round(float(P0.mean()), 2), mean_pressure_after_m=round(float(P1.mean()), 2),
                         night_pressure_before_m=round(float(P0[1:5].mean()), 2), night_pressure_after_m=round(float(P1[1:5].mean()), 2),
                         min_pressure_after_m=round(float(P1.min()), 2),
                         leakage_reduction=dict(N1_0_5=round(float(1 - (ratio ** 0.5).mean()), 4),
                                                N1_1_0=round(float(1 - (ratio ** 1.0).mean()), 4),
                                                N1_1_5=round(float(1 - (ratio ** 1.5).mean()), 4)),
                         junctions_already_below_floor=below0))
    node_ratio = {}
    for a in areas:
        for n in customers[a["id"]]:
            node_ratio[n] = [round(float(after[h][n] / before[h][n]), 4) if before[h][n] > 0 else 1.0 for h in HOURS]
    node_drop = {n: round(float(np.mean([before[h][n] - after[h][n] for h in HOURS])), 2) for n in node_ratio}
    return dict(min_service_m=min_service, margin_m=margin, n1=N1, areas=rows, node_ratio=node_ratio, node_drop_m=node_drop)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("--min", type=float, default=MIN_SERVICE_M)
    ap.add_argument("--margin", type=float, default=MARGIN_M)
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    res = optimise(os.path.abspath(a.inp), a.min, a.margin)
    os.makedirs(a.out, exist_ok=True)
    json.dump(res, open(os.path.join(a.out, "pressure_management.json"), "w"), indent=1)
    for r in res["areas"]:
        print(f"{r['id']} ({', '.join(r['prvs'])}): mean pressure {r['mean_pressure_before_m']} -> {r['mean_pressure_after_m']} m, "
              f"leakage -{r['leakage_reduction']['N1_1_0']:.0%} (N1=1.0)")


if __name__ == "__main__":
    main()
