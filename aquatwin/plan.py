"""Planning mode: only the pipe network (.inp) is needed.

    python -m aquatwin.plan network.inp [--sensors N] [--existing n1,n2,...] [--out DIR]

1. Proposed metered zones: the network is cut at PRVs, pumps and source
   mains (pipes leaving reservoirs and tanks): where inlet meters go.
2. Pressure-logger placement: leak signatures from the model at 03:00 for
   every junction; sensors are added greedily, each one where it makes the
   most not-yet-covered leak locations detectable.
3. Coverage report for 1..N sensors: share of junctions where a 2.5 L/s leak
   moves at least one sensor by 0.1 m (detectable), and share whose
   signature is distinguishable from every junction more than 300 m away
   (localisable to within 300 m).
"""
import argparse
import json
import math
import os
from multiprocessing import Pool, cpu_count

import numpy as np
import wntr

from . import network as N
from . import ui

Q_LEAK = 2.5          # L/s
DETECT_M = 0.03       # m pressure change a logger resolves on a 2-hour night average
NOISE_M = 0.02        # m noise on a night-average pressure reading
HOUR = 3
DRAWS = 3             # noisy repeats per simulated leak


def boundaries(wn):
    out = []
    for name, l in wn.links():
        if l.link_type == "Pump" or (l.link_type == "Valve"):
            out.append(name)
        elif l.start_node_name in wn.reservoir_name_list or l.end_node_name in wn.reservoir_name_list:
            out.append(name)
        elif l.start_node_name in wn.tank_name_list or l.end_node_name in wn.tank_name_list:
            out.append(name)
    return out


def propose_dmas(wn, max_junctions, fixed_cuts):
    """Split the network into district metered areas of at most max_junctions
    junctions, cutting as few pipes as possible (Kernighan-Lin bisection,
    repeated). Returns the pipes that need a boundary flow meter."""
    import networkx as nx
    from networkx.algorithms.community import kernighan_lin_bisection
    G = nx.Graph()
    for name, l in wn.links():
        if name in fixed_cuts:
            continue
        G.add_edge(l.start_node_name, l.end_node_name, name=name, weight=1)
    cuts = []
    queue = [set(c) for c in nx.connected_components(G)]
    while queue:
        part = queue.pop()
        js = [n for n in part if wn.get_node(n).node_type == "Junction"]
        if len(js) <= max_junctions:
            continue
        H = G.subgraph(part)
        best = None
        for seed in range(12):                 # keep the split that needs the fewest meters
            a, b = kernighan_lin_bisection(H, max_iter=50, seed=seed)
            cut = [d["name"] for u, v, d in H.edges(data=True) if (u in a) != (v in a)]
            if cut and (best is None or len(cut) < len(best[2])):
                best = (a, b, cut)
        if best is None or len(best[2]) > 8:   # a split needing many meters is not worth it
            continue
        a, b, cut = best
        cuts += cut
        queue += [set(a), set(b)]
    return cuts


def _sim(args):
    inp, node, q = args
    try:
        wn = wntr.network.WaterNetworkModel(inp)
        wn.options.time.duration = 0
        wn.options.time.pattern_start = HOUR * 3600
        if node:
            wn.get_node(node).add_demand(q, None)
        prefix = os.path.join(os.environ.get("TEMP", "."), f"aqp_{os.getpid()}")
        r = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=prefix)
        return r.node["pressure"].iloc[0][list(wn.junction_name_list)].values.astype(float)
    except Exception:
        return None


def signatures_all(inp, junctions):
    base = _sim((inp, None, 0))
    with Pool(max(1, cpu_count() - 1)) as pool:
        res = pool.map(_sim, [(inp, n, Q_LEAK / 1000) for n in junctions], chunksize=8)
    ok = [i for i, r in enumerate(res) if r is not None]
    S = np.stack([res[i] - base for i in ok])            # m, for a Q_LEAK leak; rows: leak node, cols: junction
    return [junctions[i] for i in ok], S


def localisation_rate(S, sel, near, rows=None, seed=0, draws=None):
    """Simulated localisation: for each leak location (row), add noise to its
    signature on the sensors `sel`, pick the best-matching location (free leak
    size, as the live system does) and count it right if within 300 m."""
    if not sel:
        return 0.0
    rows = np.arange(S.shape[0]) if rows is None else rows
    X = S[:, sel]                                   # candidates
    xn = np.maximum((X ** 2).sum(1), 1e-12)
    rng = np.random.default_rng(seed)
    ok = 0
    draws = draws or DRAWS
    for _ in range(draws):
        Y = S[rows][:, sel] + rng.normal(0, NOISE_M, (len(rows), len(sel)))
        dot = Y @ X.T                               # leaks lower pressure: same-sign match only
        score = np.where(dot > 0, dot ** 2 / xn[None, :], -1)
        best = score.argmax(1)
        detect = np.abs(S[rows][:, sel]).max(1) >= DETECT_M
        ok += int((near[rows, best] & detect).sum())
    return ok / (draws * len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("--sensors", type=int, default=0, help="number of pressure loggers (default: 1 per 30 pipes)")
    ap.add_argument("--existing", default="", help="comma-separated junctions that already have loggers")
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    inp = os.path.abspath(a.inp)
    name = a.name or os.path.splitext(os.path.basename(inp))[0]
    out = a.out or os.path.join(os.path.dirname(inp), f"aquatwin_plan_{name}")
    os.makedirs(out, exist_ok=True)
    plan = make_plan(inp, name, a.sensors, [s for s in a.existing.split(",") if s], out)
    print(json.dumps({k: v for k, v in plan.items() if k not in ("curve", "sensors", "boundaries", "zones")}, indent=1))
    print("wrote", out)


def network_health(inp, progress=print):
    """Pressure management and water quality for the plan page."""
    from . import pressure, quality
    progress("smart pressure management: finding how far each PRV can be turned down, hour by hour...")
    pm = pressure.optimise(inp, progress=lambda s: None)
    for r in pm.get("areas", []):
        progress(f"  {r['id']} ({', '.join(r['prvs'])}): average pressure {r['mean_pressure_before_m']} -> "
                 f"{r['mean_pressure_after_m']} m, leakage -{r['leakage_reduction']['N1_1_0']:.0%}")
    if not pm.get("areas"):
        progress("  " + pm.get("note", "no PRVs found"))
    progress("water quality: simulating water age and chlorine decay...")
    wq = quality.analyse(inp, progress=lambda s: progress("  " + s))
    return pm, wq


def make_plan(inp, name, k=0, existing=None, out=".", progress=print, max_zone_junctions=300, health=True):
    existing = existing or []
    os.makedirs(out, exist_ok=True)
    wn = N.load_model(inp)
    junctions = list(wn.junction_name_list)
    k = k or max(5, math.ceil(len(wn.pipe_name_list) / 30))
    bnd = boundaries(wn)
    dma = propose_dmas(wn, max_zone_junctions, set(bnd))
    if dma:
        progress(f"proposed {len(dma)} extra district boundary meter(s) to keep zones under {max_zone_junctions} junctions: {dma}")
    bnd = bnd + dma
    zones = [z for z in N.find_zones(wn, set(bnd), set(), [], 2.0) if len(z["junctions"]) >= 5]
    for i, z in enumerate(zones):
        z["id"] = f"Z{i + 1}"
        z["mode"] = "mnf"
    progress(f"{len(junctions)} junctions, {len(wn.pipe_name_list)} pipes; {len(zones)} proposed zones; "
             f"building leak signatures for every junction...")
    nodes, S = signatures_all(inp, junctions)
    col = {n: i for i, n in enumerate(junctions)}
    dist = N.Distances(wn)
    progress("computing pipe distances...")
    near = np.zeros((len(nodes), len(nodes)), dtype=bool)
    for i, n in enumerate(nodes):
        near[i] = np.array([dist.node(n, m) for m in nodes]) <= 300.0
    # columns of S are all junctions; restrict to junctions that have a signature row
    S = S[:, [col[n] for n in nodes]]
    col = {n: i for i, n in enumerate(nodes)}

    # greedy placement: each logger where it most improves simulated
    # localisation (plus detectability), from a spread-out candidate pool
    sel = [col[e] for e in existing if e in col]
    rng = np.random.default_rng(1)
    rows = np.sort(rng.choice(len(nodes), size=min(200, len(nodes)), replace=False))
    pool = list(range(0, len(nodes), max(1, len(nodes) // 120)))
    A = np.abs(S)
    order, curve = [], []
    progress(f"placing {k} loggers...")
    for step in range(k):
        best, best_v = None, -1.0
        for j in pool:
            if j in sel or j in order:
                continue
            ch = sel + order + [j]
            v = localisation_rate(S, ch, near, rows, seed=step, draws=1) + 0.25 * float((A[rows][:, ch].max(1) >= DETECT_M).mean())
            if v > best_v:
                best, best_v = j, v
        order.append(best)
        ch = sel + order
        curve.append(dict(sensors=len(order), detectable=round(float((A[:, ch].max(1) >= DETECT_M).mean()), 3),
                          localisable=round(localisation_rate(S, ch, near), 3)))
        progress(f"  logger {len(order)}: {nodes[best]}  localisable {curve[-1]['localisable']:.0%}")
    base_existing = None
    if sel:
        base_existing = dict(detectable=round(float((A[:, sel].max(1) >= DETECT_M).mean()), 3),
                             localisable=round(localisation_rate(S, sel, near), 3))
    junctions = nodes
    zone_rows = []
    zone_of = {n: z["id"] for z in zones for n in z["nodes"]}
    for z in zones:
        zone_rows.append(dict(id=z["id"], junctions=len(z["junctions"]), base_demand_ls=z["base_demand_ls"],
                              inlet_meters=[m for m, _ in z["meters"]],
                              loggers=sum(1 for j in order if zone_of.get(junctions[j]) == z["id"])))
    plan = dict(name=name, junctions=len(junctions), pipes=len(wn.pipe_name_list), zones=zone_rows,
                boundaries=bnd, dma_meters=dma, sensors=[junctions[j] for j in order], existing=existing,
                existing_coverage=base_existing, curve=curve,
                final=curve[-1] if curve else None, leak_ls=Q_LEAK, detect_m=DETECT_M,
                zone_members=[[junctions[j], zone_of.get(junctions[j], "")] for j in order])
    json.dump(plan, open(os.path.join(out, "plan.json"), "w"), indent=1)
    with open(os.path.join(out, "recommended_loggers.csv"), "w") as f:
        f.write("rank,junction,zone,x,y\n")
        for i, j in enumerate(order):
            n = junctions[j]
            x, y = wn.get_node(n).coordinates
            f.write(f"{i + 1},{n},{zone_of.get(n, '')},{x},{y}\n")
    pm = wq = None
    if health:
        pm, wq = network_health(inp, progress)
        plan["pressure_management"] = {k2: v for k2, v in pm.items() if k2 not in ("node_ratio", "node_drop_m")}
        plan["water_quality"] = {k2: v for k2, v in wq.items() if not k2.startswith("node_")}
        json.dump(plan, open(os.path.join(out, "plan.json"), "w"), indent=1)
    ui.export_plan(out, name, wn, zones, plan, pm, wq)
    return plan


if __name__ == "__main__":
    main()
