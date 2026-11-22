"""Water quality from the twin: water age and free-chlorine residual.

EPANET's water-quality engine runs for several days on the network's own
demand patterns until it settles; the last 24 hours are used.

  water age   hours since the water left a source; high age means stale water
  chlorine    1.0 mg/L dosed at every source, first-order bulk decay
              (kb = 0.5 per day, a typical treated-water value) and wall decay
              (kw = 0.1 m per day). Junctions below 0.2 mg/L, the BIS 10500 /
              CPHEEO minimum at the tap, are flagged.
Chlorine sensors are recommended at the lowest-residual junctions of each
area, at least 300 m apart: where a contamination or dosing problem shows first.

    python -m aquatwin.quality network.inp [--out DIR]
"""
import argparse
import json
import os

import networkx as nx
import numpy as np
import wntr

DOSE = 1.0          # mg/L at sources
KB = -0.5           # 1/day bulk decay
KW = -0.1           # m/day wall decay
LIMIT = 0.2         # mg/L minimum free chlorine at the tap
DAYS = 4


def _run(inp, param):
    wn = wntr.network.WaterNetworkModel(inp)
    t = wn.options.time
    t.duration = DAYS * 86400
    t.report_timestep = 3600
    t.quality_timestep = 300
    if param == "AGE":
        wn.options.quality.parameter = "AGE"
    else:
        wn.options.quality.parameter = "CHEMICAL"
        wn.options.quality.chemical_name = "Chlorine"
        wn.options.reaction.bulk_coeff = KB / 86400.0
        wn.options.reaction.wall_coeff = KW / 86400.0
        for r in wn.reservoir_name_list:
            wn.get_node(r).initial_quality = DOSE
        for tname in wn.tank_name_list:
            wn.get_node(tname).initial_quality = DOSE * 0.8
    prefix = os.path.join(os.environ.get("TEMP", "."), f"aqq_{os.getpid()}_{param}")
    r = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=prefix)
    q = r.node["quality"]
    return q[q.index >= (DAYS - 1) * 86400], wn


def analyse(inp, progress=print):
    progress("simulating water age...")
    age, wn = _run(inp, "AGE")
    progress("simulating chlorine decay...")
    cl, _ = _run(inp, "CHEMICAL")
    junc = [n for n in wn.junction_name_list
            if sum(max(0, d.base_value) for d in wn.get_node(n).demand_timeseries_list) > 0]
    age_h = (age[junc].mean() / 3600.0)
    cl_min = cl[junc].min()
    low = [n for n in junc if cl_min[n] < LIMIT]
    # areas = network cut at valves and pumps
    G = nx.Graph()
    for name, l in wn.links():
        if l.link_type == "Pipe":
            G.add_edge(l.start_node_name, l.end_node_name, weight=float(l.length))
    comp = {}
    for i, c in enumerate(nx.connected_components(G)):
        for n in c:
            comp[n] = i
    sensors = []
    for c in sorted(set(comp[n] for n in junc if n in comp)):
        members = sorted([n for n in junc if comp.get(n) == c], key=lambda n: cl_min[n])
        if len(members) < 5:
            continue
        chosen = []
        for n in members:
            if all(nx.shortest_path_length(G, n, m, weight="weight") >= 300 for m in chosen):
                chosen.append(n)
            if len(chosen) >= max(1, min(3, len(members) // 150 + 1)):
                break
        sensors += chosen
    res = dict(dose_mg_l=DOSE, kb_per_day=KB, kw_m_per_day=KW, limit_mg_l=LIMIT,
               junctions=len(junc),
               age_hours=dict(median=round(float(age_h.median()), 1), p95=round(float(age_h.quantile(0.95)), 1),
                              max=round(float(age_h.max()), 1)),
               chlorine_mg_l=dict(median=round(float(cl_min.median()), 3), p5=round(float(cl_min.quantile(0.05)), 3),
                                  min=round(float(cl_min.min()), 3)),
               below_limit=len(low), below_limit_share=round(len(low) / max(1, len(junc)), 3),
               chlorine_sensors=sensors,
               node_age_h={n: round(float(age_h[n]), 1) for n in junc},
               node_chlorine={n: round(float(cl_min[n]), 3) for n in junc})
    progress(f"water age median {res['age_hours']['median']} h (95th pct {res['age_hours']['p95']} h); "
             f"chlorine median {res['chlorine_mg_l']['median']} mg/L, {len(low)} junctions below {LIMIT} mg/L")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    res = analyse(os.path.abspath(a.inp))
    os.makedirs(a.out, exist_ok=True)
    json.dump(res, open(os.path.join(a.out, "water_quality.json"), "w"), indent=1)
    print("chlorine sensors:", res["chlorine_sensors"])


if __name__ == "__main__":
    main()
