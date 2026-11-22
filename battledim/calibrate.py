"""Calibrate the L-Town twin on the leak-free first week of 2018.

The published model's pipe roughness and demands can each be up to 10 %
off (dataset README). Like the 2020 joint winner Under Pressure, we fit
correction factors before localising:
  - Hazen-Williams roughness multiplier per district (A, B, C)
  - demand multiplier per customer type (residential, commercial, industrial)
by matching simulated to measured pressures (33 sensors) and inflows (3 meters)
at 03:00 and 12:00 on 1-7 January 2018, before the first leak (8 Jan).

Writes raw/L-TOWN_cal.inp and results/calibration.json.
"""
import json
import os

import numpy as np
import wntr
from scipy.optimize import minimize

import load
import network

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "L-TOWN_cal.inp")
HOURS = (3, 12)
DAYS = 7
PATTERNS = ("P-Residential", "P-Commercial", "P-Industrial")


def measured():
    d = load.load()
    P, F = d["pressures_2018"], d["flows_2018"]
    rows_p, rows_f = [], []
    for day in range(DAYS):
        for h in HOURS:
            a = day * 288 + h * 12
            rows_p.append(P[a:a + 12].mean(0))
            rows_f.append(F[a:a + 12].mean(0))
    return np.array(rows_p), np.array(rows_f), list(d["pressures_cols"]), list(d["flows_cols"])


def build(x, base=None):
    wn = base or network.model(network.INP)       # always start from the published model
    area = network.districts(wn)
    mC = dict(zip("ABC", x[:3]))
    mD = dict(zip(PATTERNS, x[3:6]))
    for n, p in wn.pipes():
        p.roughness *= mC[area.get(p.start_node_name, "A")]
    for n, j in wn.junctions():
        for dm in j.demand_timeseries_list:
            dm.base_value *= mD.get(dm.pattern_name, 1.0)
    return wn


def simulate(x, sensors, flows):
    wn = build(x)
    t = wn.options.time
    t.duration = DAYS * 24 * 3600
    t.report_timestep = 3600
    r = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=os.path.join(os.environ.get("TEMP", HERE), "ltcal"))
    idx = [day * 24 * 3600 + h * 3600 for day in range(DAYS) for h in HOURS]
    p = r.node["pressure"].loc[idx, sensors].values
    q = r.link["flowrate"].loc[idx, flows].values * 3600.0      # m3/h
    return p, q


def main():
    Pm, Fm, sensors, flows = measured()
    # The pump cycles on tank level and runs on different nights in the twin,
    # so compare NET inflow to districts A+B: p227 + p235 - PUMP_1.
    i1, i2, ip = flows.index("p227"), flows.index("p235"), flows.index("PUMP_1")
    net = lambda Q: Q[:, i1] + Q[:, i2] - Q[:, ip]
    net_m = net(Fm)

    def loss(x):
        try:
            p, q = simulate(x, sensors, flows)
        except Exception:
            return 1e6
        ep = (p - Pm) / 0.1                       # 10 cm pressure scale
        eq = (net(q) - net_m) / 2.0               # 2 m3/h flow scale
        return float(np.mean(ep ** 2) + np.mean(eq ** 2))

    x0 = np.ones(6)
    l0 = loss(x0)
    # bounded search: the dataset states parameter errors are within ~10 %
    res = minimize(loss, x0, method="Powell", bounds=[(0.85, 1.15)] * 6,
                   options=dict(maxfev=150, xtol=1e-3, ftol=1e-3))
    x = res.x if res.fun < l0 else x0
    l1 = loss(x)
    p0, q0 = simulate(x0, sensors, flows)
    p1, q1 = simulate(x, sensors, flows)
    fi = [i1, i2]
    rep = dict(
        factors=dict(roughness=dict(zip("ABC", np.round(x[:3], 4).tolist())),
                     demand=dict(zip(PATTERNS, np.round(x[3:], 4).tolist()))),
        loss_before=round(l0, 3), loss_after=round(l1, 3),
        pressure_rmse_m=dict(before=round(float(np.sqrt(np.mean((p0 - Pm) ** 2))), 3),
                             after=round(float(np.sqrt(np.mean((p1 - Pm) ** 2))), 3)),
        net_inflow_rmse_m3h=dict(before=round(float(np.sqrt(np.mean((net(q0) - net_m) ** 2))), 3),
                                 after=round(float(np.sqrt(np.mean((net(q1) - net_m) ** 2))), 3)),
        evaluations=int(res.nfev),
    )
    wntr.network.io.write_inpfile(build(x), OUT)
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(rep, open(os.path.join(HERE, "results", "calibration.json"), "w"), indent=2)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
