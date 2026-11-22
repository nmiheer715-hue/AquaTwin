"""Day-by-day detection and localisation (strictly causal).

Per metered zone, each morning after the night window:
  indicator  water balance (smart-metered zone) or minimum night flow
  detect     rise above the zone's reference by k_sigma x daily noise on two
             mornings, or big x that on one; a sustained drop is a repair
  localise   night pressure change since the reference, matched to the leak
             signatures (point leak + general demand change), leak size bounded
             by the flow rise; report the pipe that best covers the top candidates
  carry      at report_from: leaks still open, found by matching pursuit
             against the leak-free reference, are reported at its start
"""
from datetime import timedelta

import numpy as np
import pandas as pd


class Localiser:
    def __init__(self, sig, sensor_zone, wn, dist):
        self.nodes = list(sig["nodes"])
        self.node_zone = list(sig["node_zone"])
        self.S, self.D = sig["S"], sig["D"]
        self.zone_ids = list(sig["zone_ids"])
        self.sensor_zone = sensor_zone
        self.dist = dist
        self.pipes_of = {}
        for n, l in wn.links():
            if l.link_type == "Pipe":
                for e in (l.start_node_name, l.end_node_name):
                    self.pipes_of.setdefault(e, []).append(n)

    def _idx(self, zone):
        si = [i for i, z in enumerate(self.sensor_zone) if z == zone]
        ci = [i for i, z in enumerate(self.node_zone) if z == zone]
        return si, ci

    def rank(self, dp, zone, q_ls=None, band=(0.5, 2.0)):
        si, ci = self._idx(zone)
        if not si or not ci:
            return [self.nodes[i] for i in ci], np.zeros(len(ci))
        y, Dz = dp[si], self.D[self.zone_ids.index(zone)][si]
        res = np.full(len(ci), np.inf)
        for k, i in enumerate(ci):
            s = self.S[i, si]
            X = np.stack([s, Dz], 1)
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
            if q_ls is not None:
                m = float(np.clip(coef[0], band[0] * q_ls, band[1] * q_ls))
                c = float(Dz @ (y - m * s) / (Dz @ Dz + 1e-12))
                coef = np.array([m, c])
            elif coef[0] <= 0:
                coef = np.array([0.0, (Dz @ y) / (Dz @ Dz + 1e-12)])
            res[k] = np.sum((y - X @ coef) ** 2)
        o = np.argsort(res)
        return [self.nodes[ci[j]] for j in o], res[o]

    def choose_pipe(self, cand, res, k, tau):
        cand, res = cand[:k], np.asarray(res[:k], float)
        if not cand:
            return None
        if len(cand) == 1 or res[0] <= 0:
            w = np.ones(len(cand)) / len(cand)
        else:
            w = np.exp(-(res - res[0]) / (tau * res[0] + 1e-12))
            w /= w.sum()
        pipes = sorted({p for n in cand for p in self.pipes_of.get(n, [])})
        if not pipes:
            return None
        cost = [sum(wi * self.dist.pipe_node(p, n) for wi, n in zip(w, cand)) for p in pipes]
        return pipes[int(np.argmin(cost))]

    def pursuit(self, dp, zone, excess, q_min, max_leaks=6):
        out, r, left = [], dp.copy(), excess
        si, _ = self._idx(zone)
        if not si:
            return out
        Dz = self.D[self.zone_ids.index(zone)][si]
        for _ in range(max_leaks):
            if left < q_min:
                break
            cand, res = self.rank(r, zone, q_ls=left / 3.6, band=(0.1, 1.0))
            if not cand:
                break
            i = self.nodes.index(cand[0])
            s = self.S[i, si]
            coef, *_ = np.linalg.lstsq(np.stack([s, Dz], 1), r[si], rcond=None)
            m = float(np.clip(coef[0], 0.1 * left / 3.6, left / 3.6))
            if m * 3.6 < q_min:
                break
            out.append((self.choose_pipe(cand, res, 8, 0.25), round(m * 3.6, 2), cand[:5]))
            r = r.copy()
            r[si] = r[si] - m * s
            left -= m * 3.6
        return out


def run(cfg, sc, zones, ind, thr, pn, loc, repairs=None):
    """ind: zone -> daily indicator (weekly pattern removed); thr: zone -> m3/h;
    pn: (days, sensors) night pressures. Returns (alarms, events)."""
    warm = cfg["history_days"]
    days = len(pn)
    day0 = sc.t0
    end_h = cfg["night_window"][1]
    report_from = pd.Timestamp(cfg["report_from"]) if cfg.get("report_from") else None
    st = {z["id"]: dict(ref=float(np.median(ind[z["id"]][:warm])), pref=pn[:warm].mean(0),
                        active=[], up=0, dn=0) for z in zones}
    events, alarms = [], []
    repairs = repairs or []

    for k in range(warm, days):
        t_dec = day0 + timedelta(days=k, hours=end_h)
        for link, tr in repairs:
            if day0 + timedelta(days=k - 1, hours=end_h) < tr <= t_dec:
                for zid, s in st.items():
                    if s["active"]:
                        j = min(range(len(s["active"])), key=lambda i: loc.dist.pipe(s["active"][i]["pipe"], link))
                        if loc.dist.pipe(s["active"][j]["pipe"], link) < 800:
                            s["active"].pop(j)
                            s["ref"], s["pref"] = float(ind[zid][k]), pn[k]
        for z in zones:
            zid, s = z["id"], st[z["id"]]
            ex = ind[zid][k] - s["ref"]
            s["up"] = s["up"] + 1 if ex > thr[zid] else 0
            s["dn"] = s["dn"] + 1 if ex < -thr[zid] else 0
            if s["up"] >= 2 or ex > cfg["big"] * thr[zid]:
                dp = pn[k] - s["pref"]
                cand, res = loc.rank(dp, zid, q_ls=max(ex, thr[zid]) / 3.6)
                pipe = loc.choose_pipe(cand, res, cfg["topk"], cfg["tau"])
                if pipe is None:
                    s["ref"], s["pref"], s["up"] = float(ind[zid][k]), pn[k], 0
                    continue
                same = [e for e in s["active"] if loc.dist.pipe(e["pipe"], pipe) <= cfg["same_m"]]
                same += [e for e in events if not e["growth"] and e["zone"] == zid
                         and k - e["day"] <= cfg["dedupe_days"] and loc.dist.pipe(e["pipe"], pipe) <= 0.0]
                ev = dict(day=k, time=t_dec, zone=zid, size_m3h=round(float(ex), 2), pipe=pipe,
                          top=[str(c) for c in cand[:5]], growth=bool(same), kind="new")
                events.append(ev)
                if not same:
                    s["active"].append(ev)
                    if report_from is None or t_dec >= report_from:
                        alarms.append(ev)
                s["ref"], s["pref"], s["up"] = float(ind[zid][k]), pn[k], 0
            elif s["dn"] >= 2:
                if s["active"]:
                    j = min(range(len(s["active"])), key=lambda i: abs(s["active"][i]["size_m3h"] + ex))
                    s["active"].pop(j)
                s["ref"], s["pref"], s["dn"] = float(ind[zid][k]), pn[k], 0
        if report_from is not None and (day0 + timedelta(days=k + 1)).normalize() == report_from.normalize():
            w = cfg["carry_nights"]
            for z in zones:
                zid = z["id"]
                exz = float(np.median(ind[zid][k - w + 1:k + 1]) - np.median(ind[zid][:warm]))
                dp = pn[k - w + 1:k + 1].mean(0) - pn[:warm].mean(0)
                for pipe, size, top in loc.pursuit(dp, zid, exz, cfg["carry_qmin"] * thr[zid]):
                    if pipe and all(loc.dist.pipe(pipe, a["pipe"]) > 0 for a in alarms):
                        alarms.append(dict(day=k + 1, time=report_from + timedelta(minutes=5), zone=zid,
                                           size_m3h=size, pipe=pipe, top=[str(c) for c in top],
                                           growth=False, kind="carry"))
    alarms.sort(key=lambda a: a["time"])
    return alarms, events
