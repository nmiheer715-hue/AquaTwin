"""Day-ahead forecasting: district demand and service-tank levels.

Demand (every metered zone)
  Every midnight, forecast the next 24 hourly values of the zone's net
  inflow (consumption + losses). Gradient-boosted trees on features known at
  midnight: the same hour yesterday, the same hour last week, yesterday's
  mean, hour of day and day of week. Trained on the history before
  report_from (or the first 60 % of the data), scored on the rest against the
  two baselines utilities use: "same as yesterday" and "same as last week".

Tank level (every tank with a level sensor, a metered pump into it and
level controls in the model)
  The twin rolls tomorrow forward hour by hour: tank outflow = the demand
  forecast of the zone the tank feeds, pump on/off by the model's own level
  controls, pump flow = its measured average when running. The forecast
  trajectory is scored against the measured level, and hours below the
  model's low-level threshold are flagged.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from . import data as Dm


def hourly(sc, x):
    per_h = max(1, int(round(60 / sc.step_min)))
    n = len(x) // per_h
    return np.asarray(x[: n * per_h], float).reshape(n, per_h).mean(1)


def _features(y, t0):
    """Rows for target hours t, using values known at the midnight before t.

    Everything is scaled by the mean of the 7 days before that midnight, and the
    target is the ratio to it: trees cannot extrapolate, and leaks push a zone's
    flow above anything seen in training.
    """
    rows, idx, base = [], [], []
    for t in range(168 + 24, len(y)):
        day_start = (t // 24) * 24
        if day_start - 192 < 0:
            continue
        h = t % 24
        dow = (t // 24 + t0.dayofweek) % 7
        b = max(float(y[day_start - 168:day_start].mean()), 1e-6)
        yd = y[day_start - 24:day_start].mean()
        rows.append([y[t - 24] / b, y[t - 168] / b, y[t - 192] / b, yd / b, y[day_start - 1] / b,
                     np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24), np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)])
        idx.append(t)
        base.append(b)
    return np.array(rows), np.array(idx), np.array(base)


def demand(sc, wn, zones, cfg, progress=print):
    split_day = None
    if cfg.get("report_from"):
        split_day = (pd.Timestamp(cfg["report_from"]) - sc.t0).days
    out = {}
    for z in zones:
        y = hourly(sc, Dm.zone_net_inflow(sc, wn, z))
        y = pd.Series(y).interpolate(limit_direction="both").values
        X, idx, base = _features(y, sc.t0)
        cut = (split_day or int(0.6 * len(y) / 24)) * 24
        tr, te = idx < cut, idx >= cut
        if tr.sum() < 24 * 14 or te.sum() < 24 * 7:
            continue
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, random_state=0)
        m.fit(X[tr], y[idx[tr]] / base[tr])
        pred = m.predict(X[te]) * base[te]
        truth = y[idx[te]]
        yday = y[idx[te] - 24]
        lweek = y[idx[te] - 168]
        mape = lambda p: float(np.mean(np.abs(p - truth) / np.maximum(np.abs(truth), 1e-6)) * 100)
        rmse = lambda p: float(np.sqrt(np.mean((p - truth) ** 2)))
        fc = np.full(len(y), np.nan)
        fc[idx[te]] = pred
        out[z["id"]] = dict(
            mode=z["mode"], mean_m3h=round(float(truth.mean()), 2),
            mape_pct=dict(model=round(mape(pred), 2), same_as_yesterday=round(mape(yday), 2), same_as_last_week=round(mape(lweek), 2)),
            rmse_m3h=dict(model=round(rmse(pred), 2), same_as_yesterday=round(rmse(yday), 2), same_as_last_week=round(rmse(lweek), 2)),
            test_hours=int(te.sum()), first_test_hour=int(cut),
            _series=y, _forecast=fc)
        r = out[z["id"]]
        progress(f"  {z['id']} demand day-ahead: error {r['mape_pct']['model']}% "
                 f"(same as yesterday {r['mape_pct']['same_as_yesterday']}%, same as last week {r['mape_pct']['same_as_last_week']}%)")
    return out


def _level_rules(wn, tank):
    """(pump link, level to switch it on, level to switch it off) from the model's controls."""
    on = off = pump = None
    for _, c in wn.controls():
        s = str(c)
        if f"TANK {tank} LEVEL" not in s.upper() and f"{tank} LEVEL" not in s:
            continue
        for a in c.actions():
            link = a.target()[0]
            if link.link_type != "Pump":
                continue
            pump = link.name
            lvl = float(s.split("LEVEL")[1].split()[1])
            if "BELOW" in s and "OPEN" in s:
                on = lvl
            if "ABOVE" in s and "CLOSED" in s:
                off = lvl
    return pump, on, off


def tanks(sc, wn, zones, dem, progress=print):
    out = {}
    if sc.L is None:
        return out
    for tname in sc.L.columns:
        if tname not in wn.tank_name_list:
            continue
        zone = next((z for z in zones if tname in z["tanks_metered"]), None)
        pump, on, off = _level_rules(wn, tname)
        if zone is None or pump is None or on is None or off is None or zone["id"] not in dem or pump not in sc.F.columns:
            continue
        area = np.pi * (wn.get_node(tname).diameter / 2) ** 2
        lvl = hourly(sc, sc.L[tname].values)
        qp = hourly(sc, sc.F[pump].values)
        q_on = float(np.median(qp[qp > 0.2 * np.nanmax(qp)]))
        d = dem[zone["id"]]
        y, fc = d["_series"], d["_forecast"]
        # the tank's outflow is what the zone uses: zone net inflow minus pumping straight into it is
        # already the zone's consumption, so outflow = consumption
        start = d["first_test_hour"]
        days = (len(lvl) - start) // 24
        traj = np.full(len(lvl), np.nan)
        lows_pred = lows_true = hits = 0
        for k in range(days):
            t0 = start + 24 * k
            h = lvl[t0 - 1]
            running = qp[t0 - 1] > 0.2 * q_on
            for t in range(t0, t0 + 24):
                if h <= on:
                    running = True
                elif h >= off:
                    running = False
                q_in = q_on if running else 0.0
                h = h + (q_in - fc[t]) / area
                traj[t] = h
            p_low = bool(np.nanmin(traj[t0:t0 + 24]) < on + 0.15)
            t_low = bool(np.nanmin(lvl[t0:t0 + 24]) < on + 0.15)
            lows_pred += p_low
            lows_true += t_low
            hits += p_low and t_low
        m = ~np.isnan(traj)
        err = np.abs(traj[m] - lvl[m])
        out[tname] = dict(zone=zone["id"], pump=pump, switch_on_m=on, switch_off_m=off, pump_flow_m3h=round(q_on, 1),
                          mae_m=round(float(err.mean()), 3), p90_m=round(float(np.percentile(err, 90)), 3),
                          level_range_m=[round(float(np.nanmin(lvl)), 2), round(float(np.nanmax(lvl)), 2)],
                          low_level_days=dict(measured=int(lows_true), forecast=int(lows_pred), both=int(hits)),
                          _level=lvl, _forecast=traj)
        progress(f"  tank {tname}: day-ahead level error {out[tname]['mae_m']} m on average (90% within {out[tname]['p90_m']} m), "
                 f"level range {out[tname]['level_range_m'][0]}–{out[tname]['level_range_m'][1]} m")
    return out


def summary(dem, tk):
    clean = lambda d: {k: v for k, v in d.items() if not k.startswith("_")}
    return dict(demand={k: clean(v) for k, v in dem.items()}, tanks={k: clean(v) for k, v in tk.items()})
