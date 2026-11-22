"""District signals from SCADA: water balance (Area C) and minimum night
flow (Areas A+B), plus nightly pressures.

  Area C  fully smart-metered: loss_C = (PUMP_1 - tank storage change) - sum(AMR)
  A + B   no customer meters:  net_AB = p227 + p235 - PUMP_1; its 02:00-04:00
          average (minimum night flow, MNF) rises when a leak appears.
"""
import numpy as np

import load

TANK_AREA = np.pi * 8.0 ** 2      # T1 diameter 16 m -> m2
STEPS_PER_DAY = 288
NIGHT = (24, 48)                  # 02:00-04:00 in 5-min steps


def year_signals(d, y):
    F = d[f"flows_{y}"]
    fc = list(d["flows_cols"])
    q227, q235, qp = F[:, fc.index("p227")], F[:, fc.index("p235")], F[:, fc.index("PUMP_1")]
    lvl = d[f"levels_{y}"][:, 0]
    amr = d[f"demands_{y}"].sum(1) / 1000.0                       # m3/h
    dh = np.gradient(lvl) * 12.0                                  # m/h
    inflow_c = qp - TANK_AREA * dh
    loss_c = inflow_c - amr                                       # m3/h, 5-min resolution
    net_ab = q227 + q235 - qp
    P = d[f"pressures_{y}"]
    nd = len(F) // STEPS_PER_DAY

    def daily(x, night=False):
        x = x[: nd * STEPS_PER_DAY].reshape(nd, STEPS_PER_DAY, *x.shape[1:])
        return (x[:, NIGHT[0]:NIGHT[1]] if night else x).mean(1)

    # minimum night flow: lowest rolling 1-hour average between 00:00 and 06:00
    X = net_ab[: nd * STEPS_PER_DAY].reshape(nd, STEPS_PER_DAY)[:, :72]
    k = np.ones(12) / 12
    mnf = np.array([np.convolve(r, k, "valid").min() for r in X])
    return dict(
        days=nd,
        mnf_ab=mnf, net_ab=daily(net_ab),
        amr_night=daily(amr, True), amr=daily(amr),
        loss_c=daily(loss_c), loss_c_night=daily(loss_c, True),
        p_night=daily(P, True), q_night=daily(q227 + q235, True),
        net_ab_5min=net_ab, loss_c_5min=loss_c, amr_5min=amr,
    )


def leak_truth(d, y, areas):
    """Daily mean leak flow per area from the answer key (development only)."""
    L = d[f"leaks_{y}"]
    cols = list(d[f"leaks_cols_{y}"])
    nd = len(L) // STEPS_PER_DAY
    Ld = L[: nd * STEPS_PER_DAY].reshape(nd, STEPS_PER_DAY, -1).mean(1)
    out = {}
    for a in ("A", "B", "C"):
        idx = [i for i, c in enumerate(cols) if areas.get(c) == a]
        out[a] = Ld[:, idx].sum(1) if idx else np.zeros(nd)
    return out
