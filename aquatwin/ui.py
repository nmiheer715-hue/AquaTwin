"""Control-room and planning pages for any network (self-contained HTML)."""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PALETTE = ["#557390", "#63a27f", "#b08b5c", "#8a6fb0", "#b0606b", "#5e9fa8", "#a39a4f", "#7d8796"]


def geometry(wn, zones):
    xy = {n: wn.get_node(n).coordinates for n in wn.node_name_list}
    xs = [p[0] for p in xy.values()]
    ys = [p[1] for p in xy.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W = 1000.0
    H = W * max(y1 - y0, 1e-9) / max(x1 - x0, 1e-9)
    H = min(max(H, 300.0), 1400.0)

    def P(n):
        x, y = xy[n]
        return [round((x - x0) / max(x1 - x0, 1e-9) * W, 1), round((y1 - y) / max(y1 - y0, 1e-9) * H, 1)]

    # ground elevation of every node (reservoirs: their head), scaled 0..80 map units for the 3D view
    def elev(n):
        node = wn.get_node(n)
        if node.node_type == "Reservoir":
            return float(node.base_head)
        return float(getattr(node, "elevation", 0.0) or 0.0)
    ev_ = {n: elev(n) for n in wn.node_name_list}
    e0, e1 = min(ev_.values()), max(ev_.values())
    Z = lambda n: round((ev_[n] - e0) / (e1 - e0) * 80.0, 1) if e1 > e0 else 0.0

    zone_of = {n: z["id"] for z in zones for n in z["nodes"]}
    paths, segs, mids = {}, {}, {}
    for name, l in wn.links():
        a, b = P(l.start_node_name), P(l.end_node_name)
        za, zb = Z(l.start_node_name), Z(l.end_node_name)
        zid = zone_of.get(l.start_node_name) or zone_of.get(l.end_node_name) or "other"
        paths.setdefault(zid, []).append(f"M{a[0]} {a[1]}L{b[0]} {b[1]}")
        segs.setdefault(zid, []).extend([a[0], a[1], za, b[0], b[1], zb])
        mids[name] = [round((a[0] + b[0]) / 2, 1), round((a[1] + b[1]) / 2, 1), round((za + zb) / 2, 1)]
    zl = [dict(id=z["id"], color=PALETTE[i % len(PALETTE)], path="".join(paths.get(z["id"], [])), segs=segs.get(z["id"], []),
               label=f"{z['id']} · {len(z['junctions'])} junctions · {'water balance' if z.get('mode') == 'balance' else 'night flow'}")
          for i, z in enumerate(zones)]
    if "other" in paths:
        zl.append(dict(id="other", color="#3a4652", path="".join(paths["other"]), segs=segs["other"],
                       label="Unzoned (sources, transmission)"))
    sources = {n: P(n) + [Z(n)] for n in list(wn.reservoir_name_list) + list(wn.tank_name_list)}
    P3 = lambda n: P(n) + [Z(n)]
    return dict(W=W, H=round(H, 1), zones=zl, sources=sources, elev_range_m=[round(e0, 1), round(e1, 1)]), P3, mids


def health_data(wn, P, mids, pm, wq):
    """Per-junction layers (pressure saving, water age, chlorine) and summaries."""
    if not (pm or wq):
        return None
    nodes = sorted(set((wq or {}).get("node_age_h", {})) | set((pm or {}).get("node_drop_m", {})))
    return dict(
        nodes=[P(n) for n in nodes],
        drop=[(pm or {}).get("node_drop_m", {}).get(n) for n in nodes],
        age=[(wq or {}).get("node_age_h", {}).get(n) for n in nodes],
        chlorine=[(wq or {}).get("node_chlorine", {}).get(n) for n in nodes],
        cl_sensors=[P(n) for n in (wq or {}).get("chlorine_sensors", [])],
        prvs=[dict(id=v, p=mids[v]) for v in wn.valve_name_list if wn.get_link(v).valve_type == "PRV" and v in mids],
        pm={k: v for k, v in (pm or {}).items() if k not in ("node_ratio", "node_drop_m")},
        wq={k: v for k, v in (wq or {}).items() if not k.startswith("node_")})


def forecast_data(sc, fc, first_day):
    """Hourly forecast vs measured series from the replay's first day onward (rounded)."""
    if not fc:
        return None
    dem, tk = fc
    start_h = first_day * 24
    r = lambda a: [None if (v is None or v != v) else round(float(v), 2) for v in a[start_h:]]
    return dict(
        start_hour=start_h,
        demand={z: dict(actual=r(d["_series"]), forecast=r(d["_forecast"]), mape=d["mape_pct"], mode=d["mode"]) for z, d in dem.items()},
        tanks={t: dict(actual=r(d["_level"]), forecast=r(d["_forecast"]), mae=d["mae_m"], p90=d["p90_m"], zone=d["zone"],
                       switch_on=d["switch_on_m"], switch_off=d["switch_off_m"], low=d["low_level_days"]) for t, d in tk.items()})


def export(cfg, wn, sc, zones, sensors, alarms, ind, thr, ev, pm=None, wq=None, fc=None):
    geo, P, mids = geometry(wn, zones)
    t0 = sc.t0
    rf_day = 0
    if cfg.get("report_from"):
        import pandas as pd
        rf_day = max(0, (pd.Timestamp(cfg["report_from"]) - t0).days)
    import pandas as pd
    al = []
    for i, a in enumerate(alarms):
        al.append(dict(i=i, t=a["time"].strftime("%Y-%m-%d %H:%M"), day=(a["time"].normalize() - t0).days,
                       pipe=a["pipe"], at=mids.get(a["pipe"], [0, 0]), zone=a["zone"], size=a["size_m3h"],
                       kind=a["kind"], top=[P(n) for n in a["top"] if n in wn.node_name_list],
                       status=a.get("verdict"), leak=a.get("leak"), nearest=a.get("nearest_leak"),
                       dist=a.get("dist_m"), zone_leak=a.get("zone_leak"), value=a.get("value", 0.0)))
    days = len(next(iter(ind.values())))
    leaks = []
    if ev:
        for l in ev.get("leaks", []):
            if l["link"] in mids:
                leaks.append(dict(pipe=l["link"], at=mids[l["link"]], found=l["found"],
                                  start=max(0, (pd.Timestamp(l["start"]).normalize() - t0).days),
                                  end=(pd.Timestamp(l["end"]).normalize() - t0).days))
    data = dict(name=cfg["name"], geo=geo, sensors=[P(s) for s in sensors], alarms=al, leaks=leaks,
                health=health_data(wn, P, mids, pm, wq),
                forecast=forecast_data(sc, fc, rf_day),
                start=str(t0.date()), days=days, first_day=rf_day, night_end=cfg["night_window"][1],
                n_junctions=len(wn.junction_name_list), n_pipes=len(wn.pipe_name_list),
                series={z["id"]: [round(float(v), 3) for v in ind[z["id"]]] for z in zones},
                modes={z["id"]: z["mode"] for z in zones},
                thr={k: round(float(v), 3) for k, v in thr.items()},
                evaluation={k: v for k, v in (ev or {}).items() if k != "leaks"} or None)
    html = fill("monitor.html", data)
    open(os.path.join(cfg["outdir"], "dashboard.html"), "w", encoding="utf-8").write(html)


def fill(template, data):
    """Template + shared modules (3D terrain, .inp reader) + data -> one self-contained page."""
    t = lambda n: open(os.path.join(HERE, "templates", n), encoding="utf-8").read()
    html = t(template)
    html = html.replace("/*__TERRAIN3D__*/", t("terrain3d.js")).replace("/*__INP__*/", t("inp.js"))
    return html.replace("/*__DATA__*/", "const DATA = " + json.dumps(data, separators=(",", ":")) + ";")


def export_plan(outdir, name, wn, zones, plan, pm=None, wq=None):
    geo, P, mids = geometry(wn, zones)
    health = None
    if pm or wq:
        nodes = sorted(set((wq or {}).get("node_age_h", {})) | set((pm or {}).get("node_drop_m", {})))
        health = dict(
            nodes=[P(n) for n in nodes],
            drop=[(pm or {}).get("node_drop_m", {}).get(n) for n in nodes],
            age=[(wq or {}).get("node_age_h", {}).get(n) for n in nodes],
            chlorine=[(wq or {}).get("node_chlorine", {}).get(n) for n in nodes],
            cl_sensors=[P(n) for n in (wq or {}).get("chlorine_sensors", [])],
            prvs=[dict(id=v, p=mids[v]) for v in wn.valve_name_list if wn.get_link(v).valve_type == "PRV" and v in mids])
    data = dict(name=name, geo=geo, plan=plan, health=health,
                recommended=[dict(id=s, p=P(s), rank=i + 1) for i, s in enumerate(plan["sensors"])],
                existing=[dict(id=s, p=P(s)) for s in plan.get("existing", [])],
                boundaries=[dict(id=b, p=mids[b]) for b in plan.get("boundaries", []) if b in mids])
    open(os.path.join(outdir, "plan.html"), "w", encoding="utf-8").write(fill("plan.html", data))
