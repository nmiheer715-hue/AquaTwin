"""Simulate 90 days of SCADA for EPANET's Net3 city network, with hidden
leaks, to test AquaTwin on a network it was never tuned for.

Writes examples/net3/: Net3.inp, pressures.csv, flows.csv, levels.csv,
truth.csv (the hidden leaks) and net3.json (the AquaTwin config).
Pressure loggers are the planner's recommendation (aquatwin.plan).
"""
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd
import wntr
from wntr.library import model_library
from wntr.network.controls import Control, ControlAction, SimTimeCondition
from wntr.network import LinkStatus

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "net3")
DAYS, STEP = 90, 900
START = pd.Timestamp("2026-01-05")          # a Monday
rng = np.random.default_rng(42)


def build(leaks):
    wn = wntr.network.WaterNetworkModel(model_library.get_filepath("Net3"))
    t = wn.options.time
    t.duration, t.hydraulic_timestep, t.report_timestep, t.pattern_timestep = DAYS * 86400, STEP, STEP, 3600
    wn.options.hydraulic.demand_model = "PDD"
    wn.options.hydraulic.required_pressure, wn.options.hydraulic.minimum_pressure = 15.0, 0.0
    # Lake pump runs 01:00-15:00 every day (the original file only schedules one week)
    for name, c in list(wn.controls()):
        if "PUMP 10" in str(c) and "TIME" in str(c):
            wn.remove_control(name)
    p10 = wn.get_link("10")
    for d in range(DAYS):
        for h, st in ((1, LinkStatus.Open), (15, LinkStatus.Closed)):
            wn.add_control(f"p10_{d}_{h}", Control(SimTimeCondition(wn, "=", d * 86400 + h * 3600), ControlAction(p10, "status", st)))
    # demand: day-to-day swings and busier weekends
    day_f = rng.normal(1.0, 0.03, DAYS)
    for pname in wn.pattern_name_list:
        pat = wn.get_pattern(pname)
        base = np.array(pat.multipliers, dtype=float)
        if len(base) != 24:
            continue
        mult = []
        for d in range(DAYS):
            wk = 1.06 if (START + pd.Timedelta(days=d)).day_of_week >= 5 else 1.0
            mult.extend(list(base * day_f[d] * wk))
        pat.multipliers = mult
    for lk in leaks:
        wn.get_node(lk["node"]).add_leak(wn, area=np.pi * lk["d"] ** 2 / 4, discharge_coeff=0.75,
                                         start_time=lk["start_s"], end_time=lk["end_s"])
    return wn


def main():
    os.makedirs(OUT, exist_ok=True)
    inp = os.path.join(OUT, "Net3.inp")
    shutil.copy(model_library.get_filepath("Net3"), inp)
    wn0 = wntr.network.WaterNetworkModel(inp)
    # pressure loggers: planner's recommendation
    sys.path.insert(0, os.path.dirname(HERE))
    from aquatwin import plan
    p = plan.make_plan(inp, "Net3", 10, [], os.path.join(OUT, "plan"), progress=lambda s: None,
                       max_zone_junctions=35)
    sensors = p["sensors"]
    print("loggers (planner):", sensors, "| localisable", p["final"]["localisable"])
    print("district meters (planner):", p["dma_meters"], "| zones:", [(z["id"], z["junctions"]) for z in p["zones"]])

    cands = [n for n in wn0.junction_name_list if sum(d.base_value for d in wn0.get_node(n).demand_timeseries_list) >= 0]
    pipes_of = {}
    for name, l in wn0.links():
        if l.link_type == "Pipe":
            for e in (l.start_node_name, l.end_node_name):
                pipes_of.setdefault(e, []).append(name)
    leaks = []
    for i, day in enumerate(sorted(rng.choice(np.arange(18, 80), 5, replace=False))):
        node = str(rng.choice([n for n in cands if n in pipes_of]))
        start_s = int(day * 86400 + rng.integers(0, 86400 // STEP) * STEP)
        leaks.append(dict(node=node, link=pipes_of[node][0], d=float(rng.uniform(0.025, 0.04)),
                          start_s=start_s, end_s=int(min(DAYS * 86400 - STEP, start_s + rng.integers(12, 30) * 86400))))
    print("hidden leaks:", [(l["link"], round(l["start_s"] / 86400, 1)) for l in leaks])
    wn = build(leaks)
    r = wntr.sim.WNTRSimulator(wn).run_sim()
    idx = START + pd.to_timedelta(r.node["pressure"].index, unit="s")

    P = r.node["pressure"][sensors].copy()
    P.index = idx
    P = P + rng.normal(0, 0.02, P.shape)
    # source mains: every link leaving a reservoir (pump 335 has a bypass pipe)
    flows = [n for n, l in wn.links() if l.start_node_name in wn.reservoir_name_list or l.end_node_name in wn.reservoir_name_list]
    flows += [m for m in p["dma_meters"] if m not in flows]       # the city installs the planned district meters
    print("flow meters (source mains + district boundaries):", flows)
    F = r.link["flowrate"][flows].copy() * 3600.0          # m3/h
    F.index = idx
    F = F * (1 + rng.normal(0, 0.002, F.shape))
    tanks = list(wn.tank_name_list)
    Lv = r.node["head"][tanks].copy() - np.array([wn.get_node(t).elevation for t in tanks])
    Lv.index = idx
    Lv = Lv + rng.normal(0, 0.003, Lv.shape)
    for df, name in ((P, "pressures"), (F, "flows"), (Lv, "levels")):
        df.index.name = "timestamp"
        df.round(4).to_csv(os.path.join(OUT, f"{name}.csv"))
    lk_flow = {l["link"]: float(r.node["leak_demand"][l["node"]].values.max() * 3600) for l in leaks}
    pd.DataFrame([dict(link_id=l["link"], start=(START + pd.Timedelta(seconds=l["start_s"])).strftime("%Y-%m-%d %H:%M"),
                       end=(START + pd.Timedelta(seconds=l["end_s"])).strftime("%Y-%m-%d %H:%M"),
                       peak_m3h=round(lk_flow[l["link"]], 1)) for l in leaks]).to_csv(os.path.join(OUT, "truth.csv"), index=False)
    cfg = dict(name="Net3 city (simulated SCADA)", inp="Net3.inp", csv=dict(sep=",", decimal="."),
               pressures=["pressures.csv"], flows=["flows.csv"], levels=["levels.csv"],
               flow_units="m3/h", pattern_period="calendar", history_days=7,
               report_from=str((START + pd.Timedelta(days=14)).date()), k_sigma=4.0, outdir="out")
    json.dump(cfg, open(os.path.join(OUT, "net3.json"), "w"), indent=1)
    print("leak sizes m3/h:", lk_flow)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
