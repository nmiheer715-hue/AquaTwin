"""Leak signatures from the network model at night.

For each junction: add a leak-sized demand at the night pressure hour and
record the change at every pressure sensor (m per L/s). Per zone: the same
flow spread over all customers (general demand change). Cached per model.
"""
import hashlib
import os
from multiprocessing import Pool, cpu_count

import numpy as np
import wntr


def _model(inp, hour):
    wn = wntr.network.WaterNetworkModel(inp)
    t = wn.options.time
    t.duration = 0
    t.pattern_start = int(hour * 3600)
    return wn


def _run(args):
    inp, hour, extra, sensors, tag = args
    try:
        wn = _model(inp, hour)
        for n, q in extra.items():
            wn.get_node(n).add_demand(q, None)
        prefix = os.path.join(os.environ.get("TEMP", "."), f"aqt_{os.getpid()}_{tag}")
        r = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=prefix)
        return r.node["pressure"].iloc[0][sensors].values.astype(float)
    except Exception:
        return None


def build(cfg, wn, zones, sensors, outdir):
    hour = float(np.mean(cfg["night_pressure"]))
    q = cfg["q_leak_ls"] / 1000.0
    key = hashlib.md5((open(cfg["inp"], "rb").read() + repr((hour, q, sensors)).encode())).hexdigest()[:10]
    cache = os.path.join(outdir, f"signatures_{key}.npz")
    if os.path.exists(cache):
        return dict(np.load(cache, allow_pickle=False))
    base = _run((cfg["inp"], hour, {}, sensors, "base"))
    nodes = [n for z in zones for n in z["junctions"]]
    with Pool(max(1, cpu_count() - 1)) as pool:
        res = pool.map(_run, [(cfg["inp"], hour, {n: q}, sensors, "n") for n in nodes], chunksize=8)
    ok = [i for i, r in enumerate(res) if r is not None]
    S = np.stack([(res[i] - base) / cfg["q_leak_ls"] for i in ok])
    node_ids = [nodes[i] for i in ok]
    zone_of = {n: z["id"] for z in zones for n in z["junctions"]}
    D = []
    for z in zones:
        w = np.array([max(0.0, sum(d.base_value for d in wn.get_node(n).demand_timeseries_list)) for n in z["junctions"]])
        w = w / w.sum()
        extra = {n: q * wi for n, wi in zip(z["junctions"], w) if wi > 0}
        r = _run((cfg["inp"], hour, extra, sensors, "d"))
        D.append((r - base) / cfg["q_leak_ls"] if r is not None else np.zeros(len(sensors)))
    out = dict(nodes=np.array(node_ids), node_zone=np.array([zone_of[n] for n in node_ids]),
               S=S, D=np.stack(D), zone_ids=np.array([z["id"] for z in zones]), sensors=np.array(sensors))
    np.savez(cache, **out)
    return out
