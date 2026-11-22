"""Leak sensitivity map from the L-Town digital twin.

For every junction, add a leak-sized demand at 03:00 (night conditions,
when real utilities do leak analysis) and record how each of the 33
pressure sensors changes. Also record the 'distributed demand' signature:
the same extra flow spread across all customers of the district. The
localiser separates a point leak from a general demand change with these.

Writes sensitivity.npz:  S (nodes x sensors, m per L/s), Ddist (areas x sensors).
"""
import os
import time
from multiprocessing import Pool, cpu_count

import numpy as np
import wntr

import load
import network

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("AQUATWIN_SEN", os.path.join(HERE, "sensitivity.npz"))
Q_LEAK = 0.0025          # m3/s (2.5 L/s = 9 m3/h, typical BattLeDIM leak)
HOUR = 3


def night_model():
    wn = network.model()
    t = wn.options.time
    t.duration = 0
    t.pattern_start = HOUR * 3600
    t.hydraulic_timestep = 300
    t.report_timestep = 300
    return wn


def run(extra, sensors):
    """extra: dict node -> added demand (m3/s). Returns sensor pressures."""
    wn = night_model()
    for n, q in extra.items():
        wn.get_node(n).add_demand(q, None)
    r = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=os.path.join(
        os.environ.get("TEMP", HERE), f"lt_{os.getpid()}"))
    return r.node["pressure"].loc[0, sensors].values.astype(np.float64)


def _one(args):
    node, sensors = args
    try:
        return node, run({node: Q_LEAK}, sensors)
    except Exception:
        return node, None


def main():
    d = load.load()
    sensors = list(d["pressures_cols"])
    wn = network.model()
    area = network.districts(wn)
    junctions = list(wn.junction_name_list)
    base = run({}, sensors)

    t0 = time.time()
    with Pool(max(1, cpu_count() - 1)) as pool:
        res = dict(pool.map(_one, [(n, sensors) for n in junctions], chunksize=8))
    ok = [n for n in junctions if res[n] is not None]
    S = np.stack([(res[n] - base) / (Q_LEAK * 1000) for n in ok])     # m per L/s
    print(f"{len(ok)}/{len(junctions)} node signatures in {time.time() - t0:.0f}s")

    # distributed demand signature per district: +Q_LEAK spread by base demand
    Dd, areas = [], ["A", "B", "C"]
    for a in areas:
        nodes = [n for n in junctions if area[n] == a]
        w = np.array([sum(x.base_value for x in wn.get_node(n).demand_timeseries_list) for n in nodes])
        w = w / w.sum()
        Dd.append((run({n: Q_LEAK * wi for n, wi in zip(nodes, w) if wi > 0}, sensors) - base) / (Q_LEAK * 1000))
    np.savez(OUT, nodes=np.array(ok), sensors=np.array(sensors), S=S, Ddist=np.stack(Dd),
             areas=np.array(areas), node_area=np.array([area[n] for n in ok]), base=base)
    print("saved", OUT, "| max |S| m per L/s:", np.abs(S).max().round(3))


if __name__ == "__main__":
    main()
