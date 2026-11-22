"""SCADA loading and per-zone daily indicators.

CSV format: first column a timestamp, then one column per sensor named with
the EPANET ID (node ID for pressures, tank levels and smart meters; link ID
for flows). Several files per kind (e.g. one per year) are concatenated.
Flow sign: positive in the link's EPANET direction (start node -> end node).
"""
import numpy as np
import pandas as pd

FLOW_TO_M3H = {"m3/h": 1.0, "L/s": 3.6, "m3/s": 3600.0}
AMR_TO_M3H = {"L/h": 0.001, "m3/h": 1.0, "L/s": 3.6}


def read(files, csv):
    if not files:
        return None
    parts = [pd.read_csv(f, sep=csv["sep"], decimal=csv["decimal"], index_col=0, parse_dates=True) for f in files]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    return df.astype(float)


class Scada:
    def __init__(self, cfg):
        c = cfg["csv"]
        self.P = read(cfg["pressures"], c)
        self.F = read(cfg["flows"], c)
        self.L = read(cfg["levels"], c)
        self.A = read(cfg["amr"], c)
        if self.P is None or self.F is None:
            raise SystemExit("config needs at least pressure and flow CSVs")
        idx = self.P.index
        step = pd.Series(idx).diff().median()
        self.step_min = step.total_seconds() / 60.0
        self.per_day = int(round(24 * 60 / self.step_min))
        # align everything on the pressure timestamps
        self.F = self.F.reindex(idx).interpolate(limit=3) * FLOW_TO_M3H[cfg["flow_units"]]
        if self.L is not None:
            self.L = self.L.reindex(idx).interpolate(limit=3)
        if self.A is not None:
            self.A = self.A.reindex(idx).interpolate(limit=3) * AMR_TO_M3H[cfg["amr_units"]]
        self.P = self.P.interpolate(limit=3)
        self.t0 = idx[0].normalize()
        self.days = len(idx) // self.per_day
        self.idx = idx

    def daily(self, x, h0=None, h1=None):
        x = np.asarray(x, dtype=float)[: self.days * self.per_day]
        x = x.reshape(self.days, self.per_day, *x.shape[1:])
        if h0 is not None:
            a, b = int(h0 * self.per_day / 24), int(h1 * self.per_day / 24)
            x = x[:, a:b]
        return np.nanmean(x, axis=1)

    def mnf(self, x, h0, h1):
        """Minimum rolling 1-hour average between h0 and h1, per day."""
        x = np.asarray(x, dtype=float)[: self.days * self.per_day].reshape(self.days, self.per_day)
        a, b = int(h0 * self.per_day / 24), int(h1 * self.per_day / 24)
        w = max(1, int(round(60 / self.step_min)))
        k = np.ones(w) / w
        return np.array([np.nanmin(np.convolve(r[a:b], k, "valid")) for r in x])


def zone_net_inflow(sc, wn, zone):
    """Net water entering a zone (m3/h, per time step)."""
    q = np.zeros(len(sc.idx))
    for link, sign in zone["meters"]:
        q += sign * sc.F[link].values
    hours_per_step = sc.step_min / 60.0
    w = max(1, int(round(60 / sc.step_min)))                      # smooth levels over 1 h
    for t in zone["tanks_metered"]:
        tank = wn.get_node(t)
        area = np.pi * (tank.diameter / 2.0) ** 2
        lvl = pd.Series(sc.L[t].values).rolling(w, center=True, min_periods=1).mean().values
        dh = np.gradient(lvl) / hours_per_step                    # m/h
        q -= area * dh                                            # filling tank takes water from the zone
    return q


def zone_indicator(sc, wn, zone, cfg):
    q = zone_net_inflow(sc, wn, zone)
    if zone["mode"] == "balance":
        amr = sc.A[zone["amr"]].sum(axis=1).values
        cov = max(zone["amr_coverage"], 1e-6)
        return sc.daily(q - amr / cov)          # unmetered share assumed to follow metered customers
    return sc.mnf(q, *cfg["night_window"])


def weekly_correction(x, cfg, sc, fit_days):
    """Remove the weekly pattern learned from the first fit_days days."""
    from scipy.ndimage import median_filter
    n = len(x)
    if cfg["pattern_period"] == "day_of_year":
        doy = np.array([(sc.t0 + pd.Timedelta(days=i)).dayofyear - 1 for i in range(n)])
        wd = doy % 7
    else:
        wd = np.array([(sc.t0 + pd.Timedelta(days=i)).dayofweek for i in range(n)])
    fit = max(14, min(fit_days, n))
    h = x[:fit]
    r = h - median_filter(h, 15 if fit >= 30 else 7, mode="nearest")
    eff = np.array([np.median(r[wd[:fit] == w]) if np.any(wd[:fit] == w) else 0.0 for w in range(7)])
    return x - eff[wd], eff


def daily_noise(x, fit_days):
    d = np.diff(x[:max(14, fit_days)])
    mad = np.median(np.abs(d - np.median(d))) * 1.4826
    return mad / np.sqrt(2)
