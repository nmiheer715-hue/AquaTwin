"""Hydraulic digital twin of the water network (EPANET model run by WNTR).

The twin plays two roles:
  1. "Reality": the same network with random demand variation and injected
     leaks, which produces what the field sensors would measure.
  2. "Expectation": the nominal model the control room runs in parallel.
     Measured minus expected pressure (the residual) is what the AI reads.

This is the same model-based approach used by Global Omnium in Valencia and
by DC Water's Anomaly Leak Finder: a calibrated network model running next to
live pressure and flow data.
"""
import math

import numpy as np
import wntr
from wntr.library import model_library

NET = "Net3"            # EPANET benchmark network: 97 nodes, 119 links, 2 sources
STEP = 900              # 15 min, the usual logging interval of pressure loggers
DURATION = 24 * 3600    # one day per scenario
DISCHARGE_COEFF = 0.75  # orifice coefficient used for leak outflow
MIN_PRESSURE_M = 10.0   # junctions below this are not used as leak sites


_SCHEDULE = None


def _raw():
    wn = wntr.network.WaterNetworkModel(model_library.get_filepath(NET))
    t = wn.options.time
    t.duration = DURATION
    t.hydraulic_timestep = STEP
    t.report_timestep = STEP
    wn.options.hydraulic.demand_model = "PDD"
    wn.options.hydraulic.required_pressure = 15.0
    wn.options.hydraulic.minimum_pressure = 0.0
    return wn


def scada_schedule():
    """Pump/valve on-off times as SCADA would log them on a normal day.
    Level-triggered controls are replaced by these logged times, so the twin
    and the field run the same pump states (as when a control room feeds
    its model with live pump status)."""
    global _SCHEDULE
    if _SCHEDULE is None:
        wn = _raw()
        r = simulate(wn)
        level_links = set()
        for _, c in wn.controls():
            if "LEVEL" in str(c):
                for a in c.actions():
                    level_links.add(a.target()[0].name)
        sched = {}
        for ln in sorted(level_links):
            st = r.link["status"][ln].values
            times = r.link["status"].index.values
            changes = [(int(times[i]), int(st[i])) for i in range(1, len(st)) if st[i] != st[i - 1]]
            sched[ln] = (int(st[0]), changes)
        _SCHEDULE = sched
    return _SCHEDULE


def load(demand_seed=None, local_sd=0.05, global_sd=0.02, scale=1.0, scale_pattern=None):
    """Build the network. With a seed, demands get random variation
    (each junction +-local_sd, whole network +-global_sd) so that the
    "real" network never matches the twin exactly. `scale` multiplies all
    demands (used to compute the demand-sensitivity pattern)."""
    from wntr.network.controls import Control, ControlAction, SimTimeCondition
    from wntr.network import LinkStatus
    sched = scada_schedule()
    wn = _raw()
    for name, c in list(wn.controls()):
        if "LEVEL" in str(c):
            wn.remove_control(name)
    for ln, (init, changes) in sched.items():
        link = wn.get_link(ln)
        link.initial_status = LinkStatus(init)
        for k, (t_s, st) in enumerate(changes):
            act = ControlAction(link, "status", LinkStatus(st))
            wn.add_control(f"scada_{ln}_{k}", Control(SimTimeCondition(wn, "=", t_s), act))
    if scale != 1.0 or scale_pattern is not None:
        for _, j in wn.junctions():
            for d in j.demand_timeseries_list:
                d.base_value *= scale
                if scale_pattern is not None and d.pattern_name == scale_pattern[0]:
                    d.base_value *= scale_pattern[1]
    if demand_seed is not None:
        rng = np.random.default_rng(demand_seed)
        g = rng.normal(1.0, global_sd)
        for _, j in wn.junctions():
            for d in j.demand_timeseries_list:
                d.base_value *= max(0.0, g * rng.normal(1.0, local_sd))
    return wn


def junction_names(wn):
    return list(wn.junction_name_list)


def inlet_names(wn):
    """Metered supply points for the water balance: source outflow meters
    plus tank level sensors (level change x tank area = tank outflow).
    Their sum is the total water put into the network."""
    return list(wn.reservoir_name_list) + list(wn.tank_name_list)


def _big_customers(wn):
    """Large consumers: demand patterns used by a single junction
    (industry, institutions). Utilities put these on smart meters."""
    users = {}
    for n, j in wn.junctions():
        for d in j.demand_timeseries_list:
            if d.base_value > 0:
                users.setdefault(d.pattern_name, []).append(n)
    return [(p, ns[0]) for p, ns in sorted(users.items()) if len(ns) == 1]


def metered_customers(wn):
    return [n for _, n in _big_customers(wn)]


def metered_patterns(wn):
    return [p for p, _ in _big_customers(wn)]


def leak_area(diameter_m):
    return math.pi * diameter_m ** 2 / 4.0


def simulate(wn):
    return wntr.sim.WNTRSimulator(wn).run_sim()


def pipe_graph(wn):
    """Undirected graph weighted by pipe length (m), for distances."""
    import networkx as nx
    g = nx.Graph()
    for name, link in wn.links():
        length = getattr(link, "length", 1.0) or 1.0
        g.add_edge(link.start_node_name, link.end_node_name, weight=float(length), link=name)
    return g
