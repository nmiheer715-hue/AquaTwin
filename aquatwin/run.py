"""Run AquaTwin on any network from a config file.

    python -m aquatwin.run path/to/config.json [--truth leaks.csv]

Writes to the config's outdir:
  setup.json    zones found, meters, indicator per zone, thresholds, warnings
  alarms.csv    one row per alarm: time, zone, pipe, size, candidate nodes
  alarms.json   the same, plus every event (including growth of known leaks)
  dashboard.html  the control-room UI for this network
  evaluation.json (with --truth) leaks found within 300 m, false alarms
"""
import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C
from . import data as Dm
from . import engine
from . import network as N
from . import signatures


def setup(cfg):
    wn = N.load_model(cfg["inp"])
    sc = Dm.Scada(cfg)
    warnings = []
    flow_links = [c for c in sc.F.columns if c in wn.link_name_list]
    level_tanks = [c for c in (sc.L.columns if sc.L is not None else []) if c in wn.tank_name_list]
    amr_nodes = [c for c in (sc.A.columns if sc.A is not None else []) if c in wn.node_name_list]
    sensors = [c for c in sc.P.columns if c in wn.node_name_list]
    for kind, cols, ok in (("flow", sc.F.columns, flow_links), ("pressure", sc.P.columns, sensors)):
        bad = [c for c in cols if c not in ok]
        if bad:
            warnings.append(f"{kind} columns not found in the model and ignored: {bad[:10]}")
    zones = N.find_zones(wn, set(flow_links), set(level_tanks), amr_nodes, cfg["amr_balance_coverage"])
    on_boundary = {m for z in zones for m, _ in z["meters"]}
    for fl in flow_links:
        if fl not in on_boundary:
            warnings.append(f"flow meter on {fl} is not on a zone boundary: water can bypass it "
                            f"(a parallel pipe or loop), so it is not used. Meter the main itself.")
    zone_of = {n: z["id"] for z in zones for n in z["nodes"]}
    sensor_zone = [zone_of.get(s) for s in sensors]
    for z in zones:
        if not z["meters"]:
            warnings.append(f"{z['id']} has no boundary flow meter: its leak indicator cannot be computed")
        if z["tanks_unmetered"]:
            warnings.append(f"{z['id']} has tanks without level sensors {z['tanks_unmetered']}: water balance will be noisier")
        n_s = sum(1 for x in sensor_zone if x == z["id"])
        if n_s < 3:
            warnings.append(f"{z['id']} has {n_s} pressure sensor(s): localisation in this zone will be coarse")
    zones = [z for z in zones if z["meters"]]
    return wn, sc, zones, sensors, sensor_zone, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--truth", help="optional CSV of real leaks: link_id,start,end (for evaluation)")
    args = ap.parse_args()
    run_job(args.config, args.truth)


def run_job(config_path, truth=None, progress=print):
    print = progress
    cfg = C.load(config_path)
    os.makedirs(cfg["outdir"], exist_ok=True)

    wn, sc, zones, sensors, sensor_zone, warnings = setup(cfg)
    print(f"{cfg['name']}: {len(wn.junction_name_list)} junctions, {len(wn.pipe_name_list)} pipes, "
          f"{len(sensors)} pressure sensors, {sc.days} days of data at {sc.step_min:.0f}-min steps")
    if not zones:
        raise SystemExit("no metered zone found: the flow CSV needs columns named after EPANET link IDs "
                         "at the zone inlets")
    for z in zones:
        print(f"  {z['id']}: {len(z['junctions'])} junctions, meters {[m for m, _ in z['meters']]}, "
              f"tanks {z['tanks_metered']}, smart-meter coverage {z['amr_coverage']:.0%} -> {z['mode']}")
    for w in warnings:
        print("  warning:", w)

    fit_days = sc.days
    if cfg.get("report_from"):
        fit_days = max(14, (pd.Timestamp(cfg["report_from"]) - sc.t0).days)
    else:
        fit_days = min(sc.days, 56)
    ind, thr, info = {}, {}, {}
    for z in zones:
        raw = Dm.zone_indicator(sc, wn, z, cfg)
        corr, eff = Dm.weekly_correction(raw, cfg, sc, fit_days)
        sigma = Dm.daily_noise(corr, fit_days)
        ind[z["id"]], thr[z["id"]] = corr, cfg["k_sigma"] * sigma
        info[z["id"]] = dict(sigma_m3h=round(float(sigma), 3), threshold_m3h=round(float(thr[z["id"]]), 3),
                             weekly_effect_m3h=[round(float(e), 2) for e in eff])
        print(f"  {z['id']}: daily noise {sigma:.3f} m3/h -> threshold {thr[z['id']]:.2f} m3/h")

    P = sc.P[sensors].values
    pn = sc.daily(P, *cfg["night_pressure"])
    sig = signatures.build(cfg, wn, zones, sensors, cfg["outdir"])
    dist = N.Distances(wn)
    loc = engine.Localiser(sig, sensor_zone, wn, dist)
    repairs = []
    if cfg.get("repairs"):
        r = pd.read_csv(cfg["repairs"])
        repairs = [(str(a), pd.Timestamp(b)) for a, b in r.iloc[:, :2].values]
    alarms, events = engine.run(cfg, sc, zones, ind, thr, pn, loc, repairs)
    print(f"  {len(alarms)} alarms")

    rows = [dict(time=a["time"].strftime("%Y-%m-%d %H:%M"), zone=a["zone"], pipe=a["pipe"],
                 size_m3h=a["size_m3h"], kind=a["kind"], candidates=" ".join(a["top"])) for a in alarms]
    pd.DataFrame(rows).to_csv(os.path.join(cfg["outdir"], "alarms.csv"), index=False)
    setup_out = dict(name=cfg["name"], zones=[dict(id=z["id"], junctions=len(z["junctions"]),
                     meters=z["meters"], tanks=z["tanks_metered"], amr_coverage=z["amr_coverage"],
                     indicator=z["mode"], base_demand_ls=z["base_demand_ls"], **info[z["id"]]) for z in zones],
                     sensors=len(sensors), days=sc.days, step_min=sc.step_min, warnings=warnings)
    json.dump(setup_out, open(os.path.join(cfg["outdir"], "setup.json"), "w"), indent=2)
    ser = lambda e: {**e, "time": e["time"].strftime("%Y-%m-%d %H:%M")}
    json.dump(dict(alarms=[ser(a) for a in alarms], events=[ser(e) for e in events]),
              open(os.path.join(cfg["outdir"], "alarms.json"), "w"), indent=1)

    ev = None
    if truth:
        cfg["_data_end"] = sc.idx[-1]
        zone_of = {n: z["id"] for z in zones for n in z["nodes"]}
        ev = evaluate(truth, alarms, dist, cfg, wn, zone_of)
        json.dump(ev, open(os.path.join(cfg["outdir"], "evaluation.json"), "w"), indent=2)
        print(f"  evaluation: {ev['found']}/{ev['n_leaks']} pinpointed within 300 m, "
              f"{ev['zone_detected']}/{ev['n_leaks']} detected in the right zone "
              f"(median {ev['median_delay_days']} days), {ev['false_alarms']} alarms not within 300 m of a leak")

    pm = wq = None
    if cfg.get("health", True):
        from .plan import network_health
        pm, wq = network_health(cfg["inp"], progress=print)
        json.dump({k: v for k, v in pm.items() if k not in ("node_ratio", "node_drop_m")},
                  open(os.path.join(cfg["outdir"], "pressure_management.json"), "w"), indent=1)
        json.dump({k: v for k, v in wq.items() if not k.startswith("node_")},
                  open(os.path.join(cfg["outdir"], "water_quality.json"), "w"), indent=1)
    fc = None
    if cfg.get("forecast", True):
        from . import forecast
        print("forecasting: day-ahead demand per zone and tank levels...")
        dem = forecast.demand(sc, wn, zones, cfg, progress=print)
        tk = forecast.tanks(sc, wn, zones, dem, progress=print)
        json.dump(forecast.summary(dem, tk), open(os.path.join(cfg["outdir"], "forecast.json"), "w"), indent=1)
        fc = (dem, tk)
    from . import ui
    ui.export(cfg, wn, sc, zones, sensors, alarms, ind, thr, ev, pm, wq, fc)
    print("  wrote", cfg["outdir"])
    return dict(alarms=len(alarms), evaluation=ev, outdir=cfg["outdir"])


def evaluate(path, alarms, dist, cfg, wn=None, zone_of=None):
    t = pd.read_csv(path)
    leaks = [dict(link=str(r[0]), start=pd.Timestamp(r[1]), end=pd.Timestamp(r[2])) for r in t.iloc[:, :3].values]
    rf = pd.Timestamp(cfg["report_from"]) if cfg.get("report_from") else None
    if rf is not None:
        leaks = [l for l in leaks if l["end"] >= rf]
    found, fa, verdict = set(), 0, []
    for a in alarms:
        ok = [i for i, l in enumerate(leaks) if l["start"] <= a["time"] <= l["end"] and dist.pipe(a["pipe"], l["link"]) <= 300]
        new = [i for i in ok if i not in found]
        if new:
            i = min(new, key=lambda j: dist.pipe(a["pipe"], leaks[j]["link"]))
            found.add(i)
            verdict.append(("hit", leaks[i]["link"]))
        elif ok:
            verdict.append(("repeat", None))
        else:
            fa += 1
            verdict.append(("false", None))
    end_time = cfg.get("_data_end")
    cost = float(cfg.get("cost_per_m3", 20.0))
    in_zone = set(found)
    for a, (v, l) in zip(alarms, verdict):
        a["verdict"], a["leak"] = v, l
        active = [x for x in leaks if x["start"] <= a["time"] <= x["end"]]
        if active:
            near = min(active, key=lambda x: dist.pipe(a["pipe"], x["link"]))
            a["nearest_leak"], a["dist_m"] = near["link"], round(float(dist.pipe(a["pipe"], near["link"])), 1)
        else:
            a["nearest_leak"], a["dist_m"] = None, None
        a["zone_leak"] = None
        if v == "false":
            for x in active:
                if any(dist.pipe_node(x["link"], n) <= 300 for n in a["top"]):
                    a["zone_leak"] = x["link"]
                    in_zone.add(next(i for i, y in enumerate(leaks) if y is x))
                    break
        # estimated value of the water saved: leak size from the flow rise x hours from alarm to the leak's end
        a["value"] = 0.0
        if v == "hit":
            x = next(y for y in leaks if y["link"] == l)
            stop = min(x["end"], end_time) if end_time is not None else x["end"]
            hours = max(0.0, (stop - a["time"]).total_seconds() / 3600)
            a["value"] = round(max(0.0, a["size_m3h"]) * hours * cost, 2)
        else:
            a["value"] = -float(cfg.get("false_alarm_cost", 0.0)) if v == "false" else 0.0
    # zone level: an alarm in the leak's zone while it runs (what triggers a step test or acoustic survey)
    zone_hits, delays = [], []
    if wn is not None and zone_of:
        for l in leaks:
            lz = zone_of.get(wn.get_link(l["link"]).start_node_name)
            hits = [a for a in alarms if a["zone"] == lz and l["start"] <= a["time"] <= l["end"]]
            if hits:
                zone_hits.append(l["link"])
                delays.append((min(h["time"] for h in hits) - max(l["start"], rf or l["start"])).total_seconds() / 86400)
    return dict(n_leaks=len(leaks), found=len(found), false_alarms=fa,
                found_leaks=[leaks[i]["link"] for i in sorted(found)],
                missed=[l["link"] for i, l in enumerate(leaks) if i not in found],
                in_candidate_zone=len(in_zone),
                zone_detected=len(zone_hits), zone_detected_leaks=zone_hits,
                median_delay_days=round(float(np.median(delays)), 1) if delays else None,
                value_total=round(sum(a["value"] for a in alarms), 2),
                currency=cfg.get("currency", "₹"), cost_per_m3=cost,
                leaks=[dict(link=l["link"], start=l["start"].strftime("%Y-%m-%d %H:%M"),
                            end=l["end"].strftime("%Y-%m-%d %H:%M"), found=i in found)
                       for i, l in enumerate(leaks)])


if __name__ == "__main__":
    main()
