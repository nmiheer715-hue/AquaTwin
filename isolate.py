"""Automated response study: valve isolation and water saved.

For each candidate leak location the twin pre-computes what happens if the
smart valves around it are closed (customers losing pressure, demand not
served). For every detected test leak we then compare the water lost:

  Conventional  leak runs until a customer reports it or a survey finds it
                (Awareness + Location + Repair). Assumed CONVENTIONAL_H.
  This system   alarm -> 1 h evidence -> valve closes (15 min actuation).
                If the top-ranked node is wrong but the leak is in the top-5
                zone, an acoustic crew pinpoints it (CREW_PINPOINT_H) and
                isolates it. Outside the top-5: wider crew search (CREW_WIDE_H).

A sample of scenarios is re-simulated with the valve closure to check that
the leak flow really stops.

Usage:  python isolate.py
"""
import json
import os
from multiprocessing import Pool, cpu_count

import numpy as np

import twin

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
DATA = os.path.join(HERE, "data", "dataset.npz")

CONVENTIONAL_H = 72.0     # typical reported-leak run time; unreported leaks run far longer
CREW_PINPOINT_H = 4.0     # acoustic pinpointing inside a 5-node zone
CREW_WIDE_H = 24.0        # crew search when the zone is wrong
EVIDENCE_H = 1.0          # evidence window after the alarm
VALVE_H = 0.25            # motorised valve actuation
COST_PER_KL = 20.0        # INR per kilolitre, treated-water production cost (assumption)
LOW_P = 10.0              # m, below this a customer is counted as without supply


def isolation_links(wn, node):
    return [ln for ln in wn.get_links_for_node(node) if wn.get_link(ln).link_type == "Pipe"]


def impact(node):
    """Close the pipes around `node` from t=0 on the nominal network; return
    the junctions that drop below LOW_P and the share of demand not served."""
    try:
        wn = twin.load()
        for ln in isolation_links(wn, node):
            wn.get_link(ln).initial_status = wntr_closed()
        r = twin.simulate(wn)
        p = r.node["pressure"][twin.junction_names(wn)]
        base = twin.simulate(twin.load())
        d0 = base.node["demand"][twin.junction_names(wn)].clip(lower=0).sum().sum()
        d1 = r.node["demand"][twin.junction_names(wn)].clip(lower=0).sum().sum()
        lows = [j for j in p.columns if j != node and p[j].min() < LOW_P <= base.node["pressure"][j].min()]
        return node, dict(links=isolation_links(wn, node), customers_affected=len(lows),
                          demand_unserved_pct=float(100 * max(0.0, d0 - d1) / d0))
    except Exception as e:
        return node, dict(error=str(e))


def wntr_closed():
    from wntr.network import LinkStatus
    return LinkStatus.Closed


def verify(args):
    """Re-run one scenario with the valves closing at t_close."""
    node, diam, start, seed, close_node, t_close = args
    from wntr.network.controls import Control, ControlAction, SimTimeCondition
    from wntr.network import LinkStatus
    wn = twin.load(demand_seed=seed)
    wn.get_node(node).add_leak(wn, area=twin.leak_area(diam), discharge_coeff=twin.DISCHARGE_COEFF,
                               start_time=start)
    for k, ln in enumerate(isolation_links(wn, close_node)):
        act = ControlAction(wn.get_link(ln), "status", LinkStatus.Closed)
        wn.add_control(f"iso{k}", Control(SimTimeCondition(wn, "=", t_close), act))
    try:
        r = twin.simulate(wn)
    except Exception:
        return None
    q = r.node["leak_demand"][node].values
    t = r.node["leak_demand"].index.values
    before = q[(t >= start) & (t < t_close)].mean()
    after = q[t >= t_close + twin.STEP].mean()
    return float(before * 1000), float(after * 1000)


def main():
    d = np.load(DATA)
    preds = json.load(open(os.path.join(RES, "predictions.json")))
    cands = list(d["sig_node"])

    with Pool(max(1, cpu_count() - 1)) as pool:
        imp = dict(pool.map(impact, cands))

    rows = []
    for p in preds:
        if not p["detected"]:
            continue
        q_ls = p["flow_ls"]
        delay_h = (p["detect_step"] - p["start_step"]) * twin.STEP / 3600
        t_auto = delay_h + EVIDENCE_H + VALVE_H
        top1, top5 = p["top5"][0], p["top5"]
        if top1 == p["node"]:
            t_stop, how = t_auto, "auto-isolated"
        elif p["node"] in top5:
            t_stop, how = t_auto + CREW_PINPOINT_H, "zone + acoustic pinpoint"
        else:
            t_stop, how = t_auto + CREW_WIDE_H, "wider crew search"
        rows.append(dict(scenario=p["scenario"], flow_ls=q_ls, t_stop_h=t_stop, how=how,
                         lost_kl_system=q_ls * 3.6 * t_stop, lost_kl_conventional=q_ls * 3.6 * CONVENTIONAL_H,
                         customers_affected=imp.get(p["node"], {}).get("customers_affected")))

    # verification sims: valve closes on the true node, 1.25 h after the alarm
    leak_idx = {i: k for k, i in enumerate(range(len(d["leak_node"])))}
    ver_args = []
    for p in [p for p in preds if p["detected"] and p["top5"][0] == p["node"]][:40]:
        i = p["scenario"]
        t_close = int(p["detect_step"] + (EVIDENCE_H + VALVE_H) * 4) * twin.STEP
        if t_close < twin.DURATION - 2 * 3600:
            ver_args.append((str(d["leak_node"][i]), float(d["leak_diam"][i]), int(d["leak_start"][i]),
                             int(d["leak_seed"][i]), p["node"], t_close))
    with Pool(max(1, cpu_count() - 1)) as pool:
        ver = [v for v in pool.map(verify, ver_args) if v is not None]

    sys_kl = sum(r["lost_kl_system"] for r in rows)
    conv_kl = sum(r["lost_kl_conventional"] for r in rows)
    hows = {}
    for r in rows:
        hows[r["how"]] = hows.get(r["how"], 0) + 1
    aff = [v["customers_affected"] for v in imp.values() if "customers_affected" in v]
    out = dict(
        assumptions=dict(conventional_run_h=CONVENTIONAL_H, crew_pinpoint_h=CREW_PINPOINT_H,
                         crew_wide_h=CREW_WIDE_H, evidence_h=EVIDENCE_H, valve_h=VALVE_H,
                         cost_inr_per_kl=COST_PER_KL),
        detected_leaks=len(rows), outcome_counts=hows,
        median_time_to_stop_h=float(np.median([r["t_stop_h"] for r in rows])) if rows else None,
        water_lost_kl=dict(system=sys_kl, conventional=conv_kl,
                           saved_pct=float(100 * (1 - sys_kl / conv_kl)) if conv_kl else None),
        cost_saved_inr=(conv_kl - sys_kl) * COST_PER_KL,
        per_leak_saved_kl_median=float(np.median([r["lost_kl_conventional"] - r["lost_kl_system"] for r in rows])) if rows else None,
        isolation_impact=dict(median_customers_affected=float(np.median(aff)) if aff else None,
                              max_customers_affected=int(max(aff)) if aff else None,
                              total_junctions=len(d["nodes"])),
        valve_verification=dict(n=len(ver),
                                leak_flow_before_ls_median=float(np.median([v[0] for v in ver])) if ver else None,
                                leak_flow_after_ls_median=float(np.median([v[1] for v in ver])) if ver else None,
                                stopped_share=float(np.mean([v[1] < 0.05 * max(v[0], 1e-6) for v in ver])) if ver else None),
    )
    with open(os.path.join(RES, "isolation.json"), "w") as f:
        json.dump(dict(summary=out, impact=imp, rows=rows), f, indent=2)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
