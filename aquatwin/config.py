"""Config loading. Paths in the config are relative to the config file."""
import json
import os

DEFAULTS = dict(
    name="Network",
    csv=dict(sep=",", decimal="."),
    flow_units="m3/h",          # m3/h | L/s | m3/s
    amr_units="L/h",            # L/h | m3/h | L/s
    pressures=[], flows=[], levels=[], amr=[],
    history_days=7,             # leak-free start period: reference state and calibration
    pattern_period="calendar",  # calendar (Mon..Sun) | day_of_year (pattern restarts each 1 Jan)
    night_window=[0, 6],        # hours searched for the minimum night flow
    night_pressure=[2, 4],      # hours averaged for the night pressure state
    k_sigma=4.0,                # alarm threshold in units of measured daily noise
    big=3.0,                    # x threshold: confirm on a single night
    amr_balance_coverage=0.9,   # share of a zone's demand on smart meters to use a water balance
    report_from=None,           # "YYYY-MM-DD": alarms before this are history; leaks still open are reported at its start
    carry_nights=14, carry_qmin=2.0,
    topk=12, tau=0.1, same_m=0.0, dedupe_days=120,
    q_leak_ls=2.5,              # leak size used to build signatures (L/s)
    repairs=None,               # optional CSV: link_id, repaired_at
    currency="₹",               # for the water value saved (evaluation only)
    cost_per_m3=20.0,           # treated-water cost per m3
    false_alarm_cost=0.0,       # cost charged per false alarm in the value total (BattLeDIM: 500)
    outdir="aquatwin_out",
)


def load(path):
    path = os.path.abspath(path)
    base = os.path.dirname(path)
    cfg = dict(DEFAULTS)
    user = json.load(open(path, encoding="utf-8-sig"))     # tolerate a BOM (Windows Notepad)
    cfg.update(user)
    cfg["csv"] = {**DEFAULTS["csv"], **user.get("csv", {})}

    def rel(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))

    cfg["inp"] = rel(cfg["inp"])
    for k in ("pressures", "flows", "levels", "amr"):
        v = cfg.get(k) or []
        cfg[k] = [rel(x) for x in (v if isinstance(v, list) else [v])]
    if cfg.get("repairs"):
        cfg["repairs"] = rel(cfg["repairs"])
    cfg["outdir"] = rel(cfg["outdir"])
    cfg["_config_path"] = path
    return cfg
