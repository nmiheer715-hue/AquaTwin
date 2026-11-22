"""Figures for the BattLeDIM (L-Town) results. Writes PNGs to figures/."""
import json
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import detect
import load
import network
import scoring
import signals

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
INK, MUTED, GRID = "#1d2733", "#6b7785", "#e3e8ee"
BLUE, RED, GREEN, AMBER = "#1f6feb", "#d1242f", "#1a7f37", "#bf8700"
AREA_COL = {"A": "#c9d3dd", "B": "#e8c9a8", "C": "#b9dcc4"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "figure.dpi": 150, "savefig.bbox": "tight"})


def network_map(res):
    wn = network.model()
    area = network.districts(wn)
    xy = {n: wn.get_node(n).coordinates for n in wn.node_name_list}
    fig, ax = plt.subplots(figsize=(10, 8))
    for name, l in wn.links():
        a, b = xy[l.start_node_name], xy[l.end_node_name]
        ax.plot([a[0], b[0]], [a[1], b[1]], color=AREA_COL[area.get(l.start_node_name, "A")], lw=1.6, zorder=1)
    d = load.load()
    S = np.array([xy[s] for s in d["pressures_cols"]])
    ax.scatter(S[:, 0], S[:, 1], s=45, color=BLUE, edgecolor="white", lw=0.8, zorder=4)
    amr = np.array([xy[s] for s in d["demands_cols"]])
    ax.scatter(amr[:, 0], amr[:, 1], s=6, color=GREEN, zorder=3)
    for n in ("R1", "R2", "T1"):
        ax.scatter(*xy[n], s=150, marker="s", color=INK, zorder=5)
        ax.annotate(n, xy[n], xytext=(6, 6), textcoords="offset points", fontsize=9, color=INK)

    def mid(p):
        l = wn.get_link(p)
        a, b = xy[l.start_node_name], xy[l.end_node_name]
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    det = set(res["detected"])
    for lk in scoring.leak_table(2019):
        m = mid(lk["link"])
        ax.scatter(*m, s=170, marker="X", color=GREEN if lk["link"] in det else RED,
                   edgecolor="white", lw=1, zorder=6)
    for r in res["rows"]:
        m = mid(r["link"])
        ax.scatter(*m, s=90, facecolor="none", edgecolor=AMBER, lw=2, zorder=7)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    h = [Patch(color=AREA_COL["A"], label="District A (gravity, PRV-fed)"),
         Patch(color=AREA_COL["B"], label="District B (behind PRV-3)"),
         Patch(color=AREA_COL["C"], label="District C (pumped, smart-metered)"),
         Line2D([], [], marker="o", ls="", color=BLUE, ms=8, label="Pressure sensor (33)"),
         Line2D([], [], marker="o", ls="", color=GREEN, ms=4, label="Smart water meter (82)"),
         Line2D([], [], marker="X", ls="", color=GREEN, ms=11, label="2019 leak found by AquaTwin"),
         Line2D([], [], marker="X", ls="", color=RED, ms=11, label="2019 leak missed"),
         Line2D([], [], marker="o", ls="", markerfacecolor="none", markeredgecolor=AMBER, mew=2, ms=10,
                label="AquaTwin report")]
    ax.legend(handles=h, loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False, fontsize=9)
    ax.set_xticks([]), ax.set_yticks([]), ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(f"L-Town (BattLeDIM 2020): {res['tp']} of {res['n_leaks']} leaks found in 2019, "
                 f"{res['fp']} false alarms", loc="left", color=INK)
    fig.savefig(os.path.join(FIG, "b1_ltown_map.png"))
    plt.close(fig)


def night_flow(res):
    d = load.load()
    s = signals.year_signals(d, 2019)
    t = signals.leak_truth(d, 2019, network.pipe_areas())
    days = np.arange(s["days"])
    dates = np.array([np.datetime64("2019-01-01") + np.timedelta64(int(k), "D") for k in days])
    fig, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    ax[0].plot(dates, s["mnf_ab"], color=BLUE, lw=1.2, label="Minimum night flow, districts A+B (measured)")
    ax[0].plot(dates, t["A"] + t["B"] + np.median(s["mnf_ab"][:7]) - (t["A"][0] + t["B"][0]), color=RED,
               lw=1, alpha=0.6, label="True leakage (answer key, offset to baseline)")
    ax[0].set_ylabel("m³/h")
    ax[0].legend(frameon=False, fontsize=9, loc="upper left")
    ax[1].plot(dates, s["loss_c"], color=GREEN, lw=1.2, label="Water-balance loss, district C (measured)")
    ax[1].plot(dates, t["C"] + np.median(s["loss_c"][:7]) - t["C"][0], color=RED, lw=1, alpha=0.6,
               label="True leakage (answer key, offset)")
    ax[1].set_ylabel("m³/h")
    ax[1].legend(frameon=False, fontsize=9, loc="upper left")
    for r in res["rows"]:
        c = GREEN if r["hit"] and r["hit"] != "repeat" else (MUTED if r["hit"] == "repeat" else AMBER)
        for a in ax:
            a.axvline(np.datetime64(r["time"]), color=c, lw=0.8, alpha=0.7)
    ax[0].set_title("2019 leak signals with AquaTwin reports (green = leak found, amber = false alarm)",
                    loc="left", color=INK, fontsize=11)
    fig.savefig(os.path.join(FIG, "b2_signals_2019.png"))
    plt.close(fig)


def leaderboard(res):
    rows = [("Tongji (CN)", 264873), ("Under Pressure (NL/DE/FR)", 260562), ("AquaTwin (ours)", res["total"]),
            ("IRI (ES/FR)", 210772), ("Leakbusters (DE/US)", 195490), ("Tsinghua (CN)", 167981),
            ("UNIFE (IT)", 127626)]
    rows.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    cols = [BLUE if "ours" in n else "#c4ccd4" for n, _ in rows]
    b = ax.barh([n for n, _ in rows], [v / 1000 for _, v in rows], color=cols, height=0.6)
    for bb, (_, v) in zip(b, rows):
        ax.text(bb.get_width(), bb.get_y() + bb.get_height() / 2, f"  €{v / 1000:,.0f}k", va="center", color=INK, fontsize=9)
    ax.set_xlabel("Economic score, 2019 evaluation year (thousand euro)")
    ax.set_xlim(0, 320)
    ax.set_title("Against the BattLeDIM 2020 top 6 (18 teams, 13 countries)\n"
                 "2020 teams submitted blind; AquaTwin is a post-competition run", loc="left", color=INK, fontsize=10)
    fig.savefig(os.path.join(FIG, "b3_leaderboard.png"))
    plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True)
    reps, _ = detect.run()
    res = scoring.score(reps, 2019)
    res["rows"] = [dict(r, time=r["time"]) for r in res["rows"]]
    network_map(res)
    night_flow(res)
    leaderboard(res)
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
