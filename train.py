"""Leak detection and localisation AI, trained and scored on the twin data.

Pipeline (what runs in the control room every 15 minutes):
  1. Residuals     measured pressure/flow minus the twin's expected values.
  2. Calibration   the twin's total-demand level is re-fitted every step from
                   the last 8 h of sensor data (ending 1 h ago), so normal
                   day-to-day demand swings are explained away.
  3. Detection     moving-average alarm on what calibration cannot explain;
                   threshold set so normal training days never alarm.
  4. Localisation  hybrid model: ExtraTrees classifier on residual features
                   + physics match against each candidate node's leak
                   signature from the twin. Output: ranked candidate nodes.

Sensor placement is optimised first, greedily, on training scenarios.

Usage:  python train.py [dataset.npz]
"""
import json
import os
import pickle
import sys

import networkx as nx
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier

import twin

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "dataset.npz")
RES = os.path.join(HERE, "results")

NOISE_P = 0.05      # m, random noise on a 15-min averaged pressure-logger reading
NOISE_Q = 0.002     # random noise on 15-min total supply, fraction of mean (0.2 %); meter bias cancels in change detection
MA = 4              # alarm moving average, samples (1 h)
WIN = 4             # evidence window after the alarm used for localisation (1 h)
CAL_WIN = 32        # calibration window (8 h)
CAL_LAG = 4         # calibration uses data up to 1 h ago
CAL_MIN = 8         # need 2 h of data before calibrating
N_SENSORS = 10      # pressure loggers installed (plus the 2 inlet flow meters)
SEED = 0


def moving_avg(x, k):
    """Trailing moving average along axis 1; first k-1 steps are NaN."""
    c = np.cumsum(x, axis=1, dtype=np.float64)
    out = np.full(x.shape, np.nan)
    out[:, k - 1] = c[:, k - 1] / k
    out[:, k:] = (c[:, k:] - c[:, :-k]) / k
    return out


class Data:
    def __init__(self, path):
        d = np.load(path, allow_pickle=False)
        self.nodes = list(d["nodes"])
        ns = int(d["n_supply"])
        pats = list(d["patterns"])
        big = [pats.index(p) for p in d["metered_pattern"]]
        dom = [k for k in range(len(pats)) if k not in big]
        self.P0 = d["P0"]
        Q0, M0 = d["Q0"][:, :ns], d["Q0"][:, ns:]
        self.Q0 = Q0
        rng = np.random.default_rng(SEED)
        self.q_sd = np.full(ns, NOISE_Q * np.abs(Q0.sum(1)).mean() / np.sqrt(ns))
        DPb, DQb = d["DP"][big], d["DQ"][big]
        self.DP, self.DQ = d["DP"][dom], d["DQ"][dom]   # only domestic demand is calibrated

        def measured(P, Q):
            """Sensor readings minus the twin, after removing the effect of the
            large customers' smart-metered demand (known exactly, 1 % noise)."""
            M = Q[..., ns:] * (1 + rng.normal(0, 0.01, Q[..., ns:].shape))
            gb = np.where(M0 > 1e-7, M / np.maximum(M0, 1e-7) - 1.0, 0.0)          # n, T, B
            R = P - self.P0 + rng.normal(0, NOISE_P, P.shape) - np.einsum("ntb,btj->ntj", gb, DPb)
            RQ = Q[..., :ns] - Q0 + rng.normal(0, self.q_sd, Q[..., :ns].shape) - np.einsum("ntb,btc->ntc", gb, DQb)
            return R, RQ

        self.R, self.RQ = measured(d["P"], d["Q"])
        self.Rn, self.RQn = measured(d["Pn"], d["Qn"])
        self.leak_node = list(d["leak_node"])
        self.leak_diam = d["leak_diam"]
        self.start = (d["leak_start"] // twin.STEP).astype(int)
        self.leak_flow = d["leak_flow"]
        self.sig = d["sigP"] - self.P0          # (c, T, N) physics signatures (20 mm leak)
        self.sig_node = list(d["sig_node"])
        self.T = self.P0.shape[0]
        self.cidx = {n: i for i, n in enumerate(self.sig_node)}
        self.y = np.array([self.cidx[n] for n in self.leak_node])


def calibrate(D, R, RQ, sensors):
    """Rolling least-squares fit of each customer group's demand level
    g_k(t) (domestic + large consumers) from the pressure loggers and the
    supply meters, over the last CAL_WIN steps ending CAL_LAG ago.
    Returns g (n, T, K)."""
    Ds = D.DP[:, :, sensors]                                   # K, T, S
    wq = 1.0 / D.q_sd ** 2
    A = (np.einsum("kts,lts->tkl", Ds, Ds) / NOISE_P ** 2
         + np.einsum("ktc,ltc,c->tkl", D.DQ, D.DQ, wq))       # T, K, K
    b = (np.einsum("nts,kts->ntk", R[:, :, sensors], Ds) / NOISE_P ** 2
         + np.einsum("ntc,ktc,c->ntk", RQ, D.DQ, wq))         # n, T, K
    K = A.shape[1]
    cA = np.concatenate([np.zeros((1, K, K)), np.cumsum(A, 0)])
    cb = np.concatenate([np.zeros((b.shape[0], 1, K)), np.cumsum(b, 1)], 1)
    g = np.zeros(b.shape)
    for t in range(D.T):
        hi = t - CAL_LAG
        lo = max(0, hi - CAL_WIN)
        if hi - lo >= CAL_MIN:
            AA = cA[hi] - cA[lo]
            AA = AA + 1e-6 * np.trace(AA) / K * np.eye(K)
            g[:, t] = np.linalg.solve(AA, (cb[:, hi] - cb[:, lo]).T).T
    return g


def explained_p(D, g, sensors, a=0, w=None):
    """Pressure change the calibrated demand explains, (n, T, S)."""
    sl = slice(a, None if w is None else a + w)
    return np.einsum("ntk,kts->nts", g, D.DP[:, sl][:, :, sensors])


STEP_GAP = 8        # step detector compares the last hour with the hour ending 2 h ago


def alarm_scores(D, R, RQ, sensors):
    """Step-change detectors, per time step, in units of sensor noise:
       zq  sudden unexplained rise in total supply (water balance; the
           15-minute version of DMA minimum-night-flow monitoring)
       zp  strongest sudden unexplained pressure drop at any logger.
    A leak starts abruptly; demand-model error drifts slowly."""
    g = calibrate(D, R, RQ, sensors)
    C = R[:, :, sensors] - explained_p(D, g, sensors)
    CQ = (RQ - np.einsum("ntk,ktc->ntc", g, D.DQ)).sum(2, keepdims=True)
    aP, aQ = moving_avg(C, MA), moving_avg(CQ, MA)[..., 0]
    zp = np.full(aQ.shape, np.nan)
    zq = np.full(aQ.shape, np.nan)
    zp[:, STEP_GAP:] = np.max(-(aP[:, STEP_GAP:] - aP[:, :-STEP_GAP]) / NOISE_P, axis=2)
    zq[:, STEP_GAP:] = (aQ[:, STEP_GAP:] - aQ[:, :-STEP_GAP]) / np.sqrt((D.q_sd ** 2).sum())
    warm = CAL_MIN + CAL_LAG + STEP_GAP
    zp[:, :warm] = np.nan
    zq[:, :warm] = np.nan
    return zq, zp, g


def evidence(D, R, RQ, g, t0, sensors):
    """Change in unexplained residual: the hour from t0 minus the hour that
    ended one alarm-window before t0. Demand levels frozen at t0. Persistent
    model error cancels; the leak's step change remains."""
    n = R.shape[0]
    r = np.zeros((n, len(sensors)))
    q = np.zeros((n, RQ.shape[2]))
    for i in range(n):
        a = int(min(t0[i], D.T - WIN))
        b = max(0, a - MA - WIN)
        gi = g[i, int(t0[i])]                                   # K
        ep = lambda s: np.einsum("k,kts->ts", gi, D.DP[:, s:s + WIN][:, :, sensors])
        eq = lambda s: np.einsum("k,ktc->tc", gi, D.DQ[:, s:s + WIN])
        r[i] = (R[i, a:a + WIN][:, sensors] - ep(a)).mean(0) - (R[i, b:b + WIN][:, sensors] - ep(b)).mean(0)
        q[i] = (RQ[i, a:a + WIN] - eq(a)).mean(0) - (RQ[i, b:b + WIN] - eq(b)).mean(0)
    return r, q


def features(D, r, q, t0):
    nrm = np.linalg.norm(r, axis=1, keepdims=True) + 1e-9
    hour = (np.minimum(t0, D.T - WIN) + WIN / 2) * twin.STEP / 3600.0
    tod = np.stack([np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)], 1)
    return np.hstack([r / NOISE_P, r / nrm, q / D.q_sd, tod])


def physics_scores(D, r, t0, sensors):
    """Cosine similarity of the observed pressure change with each
    candidate's leak signature at the same time of day (leak size unknown:
    direction only). Signatures are mean-centred so that the network-wide
    drop every leak causes does not dominate the match."""
    out = np.zeros((r.shape[0], len(D.sig_node)))
    for i in range(r.shape[0]):
        a = int(min(t0[i], D.T - WIN))
        gsig = D.sig[:, a:a + WIN][:, :, sensors].mean(axis=1)
        gsig = gsig - gsig.mean(1, keepdims=True)
        ri = r[i] - r[i].mean()
        out[i] = (gsig @ ri) / (np.linalg.norm(gsig, axis=1) * np.linalg.norm(ri) + 1e-9)
    return out


def softmax(x, beta):
    z = beta * (x - x.max(axis=1, keepdims=True))
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def place_sensors(D, idx, k):
    """Greedy placement: add the junction that most improves physics-based
    top-1 localisation on training leaks (evidence 1-2 h after the start)."""
    allj = list(range(len(D.nodes)))
    g = calibrate(D, D.R[idx], D.RQ[idx], allj)
    t0 = np.minimum(D.start[idx] + MA, D.T - WIN)
    r_all, _ = evidence(D, D.R[idx], D.RQ[idx], g, t0, allj)
    chosen, history = [], []
    for _ in range(k):
        best, best_acc = None, -1.0
        for s in allj:
            if s in chosen:
                continue
            sel = chosen + [s]
            acc = (physics_scores(D, r_all[:, sel], t0, sel).argmax(1) == D.y[idx]).mean()
            if acc > best_acc:
                best, best_acc = s, acc
        chosen.append(best)
        history.append(float(best_acc))
        print(f"  sensor {len(chosen):2d}: node {D.nodes[best]:>5}  physics top-1 (train) = {best_acc:.3f}", flush=True)
    return chosen, history


def main():
    os.makedirs(RES, exist_ok=True)
    D = Data(DATA)
    rng = np.random.default_rng(SEED)
    n = len(D.y)
    perm = rng.permutation(n)
    tr, te = perm[: int(0.7 * n)], perm[int(0.7 * n):]
    nn = D.Rn.shape[0]
    pn = rng.permutation(nn)
    ntr, nte = pn[: nn // 2], pn[nn // 2:]
    print(f"{n} leak scenarios ({len(tr)} train / {len(te)} test), {nn} normal days")

    # 1. sensor placement
    sensors, place_hist = place_sensors(D, tr[: min(len(tr), 600)], N_SENSORS)

    # 2. detection thresholds (flow and pressure) from normal training days
    zq, zp, _ = alarm_scores(D, D.Rn[ntr], D.RQn[ntr], sensors)
    thr_q, thr_p = float(np.nanmax(zq) * 1.05), float(np.nanmax(zp) * 1.05)
    zq, zp, _ = alarm_scores(D, D.Rn[nte], D.RQn[nte], sensors)
    fa_days = int(((np.nanmax(zq, 1) > thr_q) | (np.nanmax(zp, 1) > thr_p)).sum())
    thr = dict(flow_sd=thr_q, pressure_sd=thr_p)
    print(f"alarm thresholds flow {thr_q:.2f} sd, pressure {thr_p:.2f} sd; "
          f"false alarms on {fa_days}/{len(nte)} unseen normal days")

    def detect(idx):
        zq, zp, g = alarm_scores(D, D.R[idx], D.RQ[idx], sensors)
        s = np.fmax(zq / thr_q, zp / thr_p)
        tdet = np.full(len(idx), -1)
        for k, i in enumerate(idx):
            hits = np.where(s[k, D.start[i]:] > 1.0)[0]
            if len(hits):
                tdet[k] = D.start[i] + hits[0]
        return tdet, g

    tdet_te, g_te = detect(te)
    g_tr = calibrate(D, D.R[tr], D.RQ[tr], sensors)

    # 3. localisation model; training samples from several windows per leak
    Xs, ys = [], []
    for lag in (2, 3, 4, 5, 6):
        t0 = np.minimum(D.start[tr] + lag, D.T - WIN)
        r, q = evidence(D, D.R[tr], D.RQ[tr], g_tr, t0, sensors)
        Xs.append(features(D, r, q, t0))
        ys.append(D.y[tr])
    clf = ExtraTreesClassifier(n_estimators=600, max_features="sqrt", n_jobs=-1,
                               random_state=SEED, class_weight="balanced")
    clf.fit(np.vstack(Xs), np.concatenate(ys))

    # evaluate on detected test leaks; evidence = the hour after the alarm
    det = tdet_te >= 0
    te_d = te[det]
    yt = D.y[te_d]
    t0 = np.minimum(tdet_te[det], D.T - WIN)
    r, q = evidence(D, D.R[te_d], D.RQ[te_d], g_te[det], t0, sensors)
    p_ml = np.zeros((len(te_d), len(D.sig_node)))
    if len(te_d):
        p_ml[:, clf.classes_] = clf.predict_proba(features(D, r, q, t0))
    p_ph = softmax(physics_scores(D, r, t0, sensors), 30.0)
    p = 0.5 * p_ml + 0.5 * p_ph

    def topk(prob, k, mask=None):
        ids = range(len(yt)) if mask is None else np.where(mask)[0]
        v = [yt[i] in np.argsort(-prob[i])[:k] for i in ids]
        return float(np.mean(v)) if v else float("nan")

    G = twin.pipe_graph(twin.load())
    cache = {}

    def pipe_dist(a, b):
        if a not in cache:
            cache[a] = nx.single_source_dijkstra_path_length(G, a, weight="weight")
        return cache[a].get(b, np.nan)

    top1 = p.argmax(axis=1) if len(te_d) else np.array([], int)
    dists = np.array([pipe_dist(D.sig_node[top1[i]], D.sig_node[yt[i]]) for i in range(len(yt))])
    flow_ls = np.array([D.leak_flow[i, D.start[i]:].mean() * 1000 for i in range(n)])
    delay_h = (tdet_te - D.start[te]) * twin.STEP / 3600.0

    bins = [0, 1, 2, 5, 10, 20, 1000]
    by_size = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (flow_ls[te] >= lo) & (flow_ls[te] < hi)
        if m.sum():
            md = m & det
            by_size.append(dict(flow_ls=f"{lo}-{hi}" if hi < 1000 else f"{lo}+", n=int(m.sum()),
                                detected=float(det[m].mean()),
                                median_delay_h=float(np.median(delay_h[md])) if md.any() else None))

    big = flow_ls[te_d] >= 2.0
    metrics = dict(
        network=twin.NET, junctions=len(D.nodes), leak_candidates=len(D.sig_node),
        n_train=int(len(tr)), n_test=int(len(te)), n_normal_test_days=int(len(nte)),
        sensors=[D.nodes[s] for s in sensors], n_pressure_sensors=len(sensors), n_flow_meters=2,
        noise=dict(pressure_m=NOISE_P, flow_frac=NOISE_Q, demand_local_sd=0.05, demand_global_sd=0.02),
        alarm_thresholds_sd=thr, false_alarm_days=fa_days,
        supply_noise_ls=float(np.sqrt((D.q_sd ** 2).sum()) * 1000),
        mean_supply_ls=float(np.abs(D.Q0.sum(1)).mean() * 1000),
        detection_rate=float(det.mean()),
        detection_rate_ge_2ls=float(det[flow_ls[te] >= 2].mean()),
        median_detect_delay_h=float(np.median(delay_h[det])) if det.any() else None,
        localisation=dict(
            hybrid=dict(top1=topk(p, 1), top3=topk(p, 3), top5=topk(p, 5)),
            ml_only=dict(top1=topk(p_ml, 1), top5=topk(p_ml, 5)),
            physics_only=dict(top1=topk(p_ph, 1), top5=topk(p_ph, 5)),
            random_guess_top5=5 / len(D.sig_node),
            median_error_m=float(np.nanmedian(dists)) if len(dists) else None,
            p90_error_m=float(np.nanpercentile(dists, 90)) if len(dists) else None,
            within_500m=float(np.nanmean(dists <= 500)) if len(dists) else None,
            top5_ge_2ls=topk(p, 5, big),
        ),
        detection_by_leak_size=by_size,
        sensor_placement_curve=place_hist,
    )
    with open(os.path.join(RES, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    rows, pos = [], {i: k for k, i in enumerate(te_d)}
    for k, i in enumerate(te):
        d = dict(scenario=int(i), node=D.leak_node[i], diam_mm=round(float(D.leak_diam[i]) * 1000, 1),
                 start_step=int(D.start[i]), flow_ls=round(float(flow_ls[i]), 3),
                 detected=bool(tdet_te[k] >= 0), detect_step=int(tdet_te[k]))
        if i in pos:
            j = pos[i]
            order = np.argsort(-p[j])[:5]
            d.update(top5=[D.sig_node[o] for o in order], top5_prob=[round(float(p[j, o]), 3) for o in order],
                     error_m=round(float(dists[j]), 1))
        rows.append(d)
    with open(os.path.join(RES, "predictions.json"), "w") as f:
        json.dump(rows, f)
    with open(os.path.join(RES, "model.pkl"), "wb") as f:
        pickle.dump(dict(clf=clf, sensors=sensors, nodes=D.nodes, sig_node=D.sig_node, thr=thr), f)

    print(json.dumps({k: metrics[k] for k in ("detection_rate", "detection_rate_ge_2ls",
                                              "median_detect_delay_h", "false_alarm_days")}, indent=1))
    print("by size:", json.dumps(by_size))
    print("localisation:", json.dumps(metrics["localisation"], indent=1))


if __name__ == "__main__":
    main()
