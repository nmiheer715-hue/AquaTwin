"""Generate the simulated sensor dataset.

Writes data/dataset.npz with, for every scenario, the pressure at every
junction and the metered inlet flows over 24 h at 15 min steps, plus:
  - the nominal twin run (what the control room expects),
  - one reference leak per candidate node (physics signatures).

Usage:  python generate.py [n_leak] [n_noleak]
"""
import os
import sys
import time
from multiprocessing import Pool, cpu_count

import numpy as np

import twin

OUT = os.path.join(os.path.dirname(__file__), "data", "dataset.npz")


def run_one(spec):
    try:
        wn = twin.load(demand_seed=spec["seed"])
        if spec["node"] is not None:
            wn.get_node(spec["node"]).add_leak(
                wn, area=twin.leak_area(spec["diam"]),
                discharge_coeff=twin.DISCHARGE_COEFF, start_time=spec["start"])
        r = twin.simulate(wn)
        P = r.node["pressure"][twin.junction_names(wn)].values.astype(np.float32)
        Q = -r.node["demand"][twin.inlet_names(wn)].values.astype(np.float32)
        M = r.node["demand"][twin.metered_customers(wn)].values.astype(np.float32)
        Q = np.concatenate([Q, M], axis=1)   # supply meters, then customer smart meters
        if spec["node"] is not None:
            leak = r.node["leak_demand"][spec["node"]].values.astype(np.float32)
        else:
            leak = np.zeros(P.shape[0], np.float32)
        if P.shape[0] != twin.DURATION // twin.STEP + 1:
            return None
        return spec, P, Q, leak
    except Exception:
        return None


def main():
    n_leak = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    n_noleak = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    rng = np.random.default_rng(7)

    wn = twin.load()
    nodes = twin.junction_names(wn)
    base = twin.simulate(wn)
    P0 = base.node["pressure"][nodes].values.astype(np.float32)
    Q0 = -base.node["demand"][twin.inlet_names(wn)].values.astype(np.float32)
    M0 = base.node["demand"][twin.metered_customers(wn)].values.astype(np.float32)
    Q0 = np.concatenate([Q0, M0], axis=1)
    n_supply = len(twin.inlet_names(wn))
    # demand sensitivity per customer group (one per demand pattern: domestic
    # plus large metered consumers): how pressures/supply move per +100 %
    G = 0.05
    DP, DQ = [], []
    for pat in wn.pattern_name_list:
        rs = twin.simulate(twin.load(scale_pattern=(pat, 1.0 + G)))
        DP.append((rs.node["pressure"][nodes].values.astype(np.float32) - P0) / G)
        DQ.append((-rs.node["demand"][twin.inlet_names(wn)].values.astype(np.float32) - Q0[:, :n_supply]) / G)
    DP, DQ = np.stack(DP), np.stack(DQ)        # (K, T, N), (K, T, C)
    candidates = [n for i, n in enumerate(nodes) if P0[:, i].min() >= twin.MIN_PRESSURE_M]
    print(f"{len(nodes)} junctions, {len(candidates)} leak candidates, {cpu_count()} cpus")

    specs = []
    for i in range(n_leak):
        specs.append(dict(
            kind="leak", node=str(rng.choice(candidates)),
            # leak orifice 8 mm to 40 mm, log-uniform (small background leak to burst)
            diam=float(np.exp(rng.uniform(np.log(0.008), np.log(0.04)))),
            # start 10:00-22:00 so the twin always has 8 h of calibration history
            start=int(rng.integers(10 * 4, 22 * 4)) * twin.STEP,
            seed=int(rng.integers(1, 2**31))))
    for _ in range(n_noleak):
        specs.append(dict(kind="none", node=None, diam=0.0, start=0,
                          seed=int(rng.integers(1, 2**31))))
    # physics signatures: nominal demand, 20 mm leak from t=0 at each candidate
    for n in candidates:
        specs.append(dict(kind="sig", node=n, diam=0.02, start=0, seed=None))

    t0 = time.time()
    with Pool(max(1, cpu_count() - 1)) as pool:
        out = []
        for k, res in enumerate(pool.imap(run_one, specs, chunksize=4)):
            out.append(res)
            if (k + 1) % 200 == 0:
                print(f"  {k + 1}/{len(specs)} scenarios, {time.time() - t0:.0f}s", flush=True)
    ok = [o for o in out if o is not None]
    print(f"done: {len(ok)}/{len(specs)} converged in {time.time() - t0:.0f}s")

    def pack(kind):
        rows = [o for o in ok if o[0]["kind"] == kind]
        return rows

    leak_rows, none_rows, sig_rows = pack("leak"), pack("none"), pack("sig")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    np.savez_compressed(
        OUT,
        nodes=np.array(nodes), candidates=np.array(candidates), P0=P0, Q0=Q0, DP=DP, DQ=DQ,
        n_supply=n_supply, patterns=np.array(wn.pattern_name_list),
        metered=np.array(twin.metered_customers(wn)),
        metered_pattern=np.array(twin.metered_patterns(wn)),
        P=np.stack([o[1] for o in leak_rows]), Q=np.stack([o[2] for o in leak_rows]),
        leak_flow=np.stack([o[3] for o in leak_rows]),
        leak_node=np.array([o[0]["node"] for o in leak_rows]),
        leak_diam=np.array([o[0]["diam"] for o in leak_rows]),
        leak_start=np.array([o[0]["start"] for o in leak_rows]),
        leak_seed=np.array([o[0]["seed"] for o in leak_rows]),
        Pn=np.stack([o[1] for o in none_rows]), Qn=np.stack([o[2] for o in none_rows]),
        sigP=np.stack([o[1] for o in sig_rows]), sigQ=np.stack([o[2] for o in sig_rows]),
        sig_node=np.array([o[0]["node"] for o in sig_rows]),
    )
    print("saved", OUT)


if __name__ == "__main__":
    main()
