"""Figures for the concept note and demo video. Writes PNGs to figures/.

Usage:  python figures.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import train as T
import twin

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
FIG = os.path.join(HERE, "figures")

INK, MUTED, GRID = "#1d2733", "#6b7785", "#e3e8ee"
BLUE, RED, GREEN, AMBER = "#1f6feb", "#d1242f", "#1a7f37", "#bf8700"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "figure.dpi": 150, "savefig.bbox": "tight",
})


def network_map(m, preds):
    wn = twin.load()
    xy = {n: wn.get_node(n).coordinates for n in wn.node_name_list}
    fig, ax = plt.subplots(figsize=(8, 7))
    for _, link in wn.links():
        a, b = xy[link.start_node_name], xy[link.end_node_name]
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#b8c2cc", lw=1.2, zorder=1)
    J = np.array([xy[n] for n in wn.junction_name_list])
    ax.scatter(J[:, 0], J[:, 1], s=10, color="#8a96a3", zorder=2)
    for n in wn.reservoir_name_list + wn.tank_name_list:
        ax.scatter(*xy[n], s=140, marker="s", color=INK, zorder=4)
    S = np.array([xy[n] for n in m["sensors"]])
    ax.scatter(S[:, 0], S[:, 1], s=120, color=BLUE, edgecolor="white", lw=1.5, zorder=5)
    ex = next((p for p in preds if p.get("top5") and p["node"] in p["top5"][:3] and p["flow_ls"] > 5), None)
    if ex:
        Z = np.array([xy[n] for n in ex["top5"]])
        ax.scatter(Z[:, 0], Z[:, 1], s=380, color=AMBER, alpha=0.35, zorder=3)
        ax.scatter(*xy[ex["node"]], s=220, marker="X", color=RED, edgecolor="white", lw=1.2, zorder=6)
    ax.set_xticks([]), ax.set_yticks([]), ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    from matplotlib.lines import Line2D
    h = [Line2D([], [], marker="o", ls="", color=BLUE, ms=10, label=f"Pressure logger ({len(m['sensors'])})"),
         Line2D([], [], marker="s", ls="", color=INK, ms=9, label="Source / tank (flow + level metered)"),
         Line2D([], [], marker="X", ls="", color=RED, ms=11, label="Example leak"),
         Line2D([], [], marker="o", ls="", color=AMBER, alpha=0.5, ms=14, label="AI top-5 search zone")]
    ax.legend(handles=h, loc="lower left", frameon=False)
    ax.set_title("Digital twin network with optimised sensor placement", loc="left", color=INK)
    fig.savefig(os.path.join(FIG, "1_network_sensors.png"))
    plt.close(fig)


def detection_by_size(m):
    rows = m["detection_by_leak_size"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    lab = [r["flow_ls"] for r in rows]
    val = [100 * r["detected"] for r in rows]
    bars = ax.bar(lab, val, color=BLUE, width=0.6)
    for b, r in zip(bars, rows):
        txt = f"{b.get_height():.0f}%"
        if r["median_delay_h"] is not None:
            txt += f"\n{r['median_delay_h']:.1f} h"
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 2, txt, ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(0, 118)
    ax.set_xlabel("Leak size (litres per second)")
    ax.set_ylabel("Leaks detected (%)")
    ax.set_title(f"Detection rate and median time to alarm  ·  {m['false_alarm_days']} false alarms "
                 f"in {m['n_normal_test_days']} normal days", loc="left", color=INK, fontsize=11)
    fig.savefig(os.path.join(FIG, "2_detection_by_size.png"))
    plt.close(fig)


def localisation(m):
    L = m["localisation"]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    groups = ["Top-1", "Top-5"]
    series = [("Random guess", [1 / m["leak_candidates"], L["random_guess_top5"]], "#c4ccd4"),
              ("Physics match", [L["physics_only"]["top1"], L["physics_only"]["top5"]], AMBER),
              ("ML only", [L["ml_only"]["top1"], L["ml_only"]["top5"]], GREEN),
              ("Hybrid (ours)", [L["hybrid"]["top1"], L["hybrid"]["top5"]], BLUE)]
    x = np.arange(len(groups))
    w = 0.2
    for k, (name, v, c) in enumerate(series):
        b = ax.bar(x + (k - 1.5) * w, [100 * a for a in v], w, color=c, label=name)
        for bb in b:
            ax.text(bb.get_x() + bb.get_width() / 2, bb.get_height() + 1, f"{bb.get_height():.0f}",
                    ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(x, groups)
    ax.set_ylabel("Leak in the AI's shortlist (%)")
    ax.set_ylim(0, 105)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    ax.set_title(f"Localisation among {m['leak_candidates']} possible leak sites  ·  "
                 f"median error {L['median_error_m']:.0f} m of pipe", loc="left", color=INK, fontsize=11)
    fig.savefig(os.path.join(FIG, "3_localisation.png"))
    plt.close(fig)


def timeline(m, preds):
    D = T.Data(os.path.join(HERE, "data", "dataset.npz"))
    sensors = [D.nodes.index(s) for s in m["sensors"]]
    ex = next((p for p in preds if p["detected"] and p.get("top5") and p["top5"][0] == p["node"]
               and 3 < p["flow_ls"] < 15 and 30 < p["start_step"] < 60), None)
    ex = ex or next(p for p in preds if p["detected"])
    i = ex["scenario"]
    zq, zp, _ = T.alarm_scores(D, D.R[i:i + 1], D.RQ[i:i + 1], sensors)
    thr = m["alarm_thresholds_sd"]
    s = np.fmax(zq / thr["flow_sd"], zp / thr["pressure_sd"])[0]
    h = np.arange(D.T) * twin.STEP / 3600
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True, gridspec_kw=dict(height_ratios=[1, 1.2]))
    ax[0].plot(h, D.leak_flow[i] * 1000, color=RED, lw=2)
    ax[0].set_ylabel("Leak (L/s)")
    ax[0].set_title(f"One leak, end to end  ·  {ex['flow_ls']:.1f} L/s at node {ex['node']}", loc="left", color=INK)
    ax[1].plot(h, s, color=BLUE, lw=2, label="Alarm score")
    ax[1].axhline(1.0, color=MUTED, ls="--", lw=1)
    ax[1].text(0.3, 1.08, "alarm threshold (set on normal days)", color=MUTED, fontsize=8)
    ts, td = ex["start_step"] * 0.25, ex["detect_step"] * 0.25
    tv = td + 1.25
    for a in ax:
        a.axvline(ts, color=RED, lw=1, alpha=0.6)
        a.axvline(td, color=AMBER, lw=1.5)
        a.axvline(tv, color=GREEN, lw=1.5)
    ax[1].text(ts, ax[1].get_ylim()[1] * 0.92, " leak starts", color=RED, fontsize=9)
    ax[1].text(td, ax[1].get_ylim()[1] * 0.78, " alarm", color=AMBER, fontsize=9)
    ax[1].text(tv, ax[1].get_ylim()[1] * 0.64, " valve closed", color=GREEN, fontsize=9)
    ax[1].set_xlabel("Time of day (h)")
    ax[1].set_ylabel("Score / threshold")
    fig.savefig(os.path.join(FIG, "4_timeline.png"))
    plt.close(fig)


def water_saved():
    path = os.path.join(RES, "isolation.json")
    if not os.path.exists(path):
        return
    s = json.load(open(path))["summary"]
    w = s["water_lost_kl"]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    vals = [w["conventional"] / 1000, w["system"] / 1000]
    b = ax.barh(["Conventional\n(wait for report)", "AI + smart valves"], vals, color=["#c4ccd4", BLUE], height=0.55)
    for bb, v in zip(b, vals):
        ax.text(v, bb.get_y() + bb.get_height() / 2, f"  {v:,.1f} ML", va="center", color=INK)
    ax.set_xlabel("Water lost across all detected test leaks (megalitres)")
    ax.set_xlim(0, max(vals) * 1.25)
    ax.invert_yaxis()
    ax.set_title(f"{w['saved_pct']:.0f}% less water lost  ·  median {s['median_time_to_stop_h']:.1f} h from leak to shut-off",
                 loc="left", color=INK, fontsize=11)
    fig.savefig(os.path.join(FIG, "5_water_saved.png"))
    plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True)
    m = json.load(open(os.path.join(RES, "metrics.json")))
    preds = json.load(open(os.path.join(RES, "predictions.json")))
    network_map(m, preds)
    detection_by_size(m)
    localisation(m)
    timeline(m, preds)
    water_saved()
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
