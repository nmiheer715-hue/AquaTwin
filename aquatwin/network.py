"""Network model, metered zones (DMAs) and pipe distances.

Zones are found automatically: the network graph is cut at every link that
has a flow meter. Each remaining connected part that contains customers is a
metered zone. Its net inflow is the sum of its boundary meters (signed by
direction) minus the storage change of tanks inside it that have a level
sensor. Unmetered valves (e.g. a PRV between two districts) do not cut, so
such districts are merged into one zone, as a utility's water balance must.
"""
import networkx as nx
import numpy as np
import wntr


def load_model(inp):
    return wntr.network.WaterNetworkModel(inp)


def base_demand(wn, node):
    n = wn.get_node(node)
    if n.node_type != "Junction":
        return 0.0
    return float(sum(max(0.0, d.base_value) for d in n.demand_timeseries_list))


def find_zones(wn, flow_links, level_tanks, amr_nodes, coverage_needed):
    G = nx.Graph()
    for n in wn.node_name_list:
        G.add_node(n)
    for name, l in wn.links():
        if name in flow_links:
            continue
        G.add_edge(l.start_node_name, l.end_node_name)
    zones = []
    for comp in nx.connected_components(G):
        demand = sum(base_demand(wn, n) for n in comp)
        junctions = [n for n in comp if wn.get_node(n).node_type == "Junction"]
        if demand <= 0 or not junctions:
            continue
        meters = []
        for name in flow_links:
            l = wn.get_link(name)
            a, b = l.start_node_name in comp, l.end_node_name in comp
            if a != b:
                meters.append((name, +1 if b else -1))       # +1: flow in link direction enters the zone
        tanks = [t for t in wn.tank_name_list if t in comp]
        amr_in = [n for n in amr_nodes if n in comp]
        amr_cov = sum(base_demand(wn, n) for n in amr_in) / demand
        zones.append(dict(
            nodes=set(comp), junctions=junctions, meters=meters,
            tanks_metered=[t for t in tanks if t in level_tanks],
            tanks_unmetered=[t for t in tanks if t not in level_tanks],
            amr=amr_in, amr_coverage=round(amr_cov, 3),
            mode="balance" if amr_cov >= coverage_needed else "mnf",
            base_demand_ls=round(demand * 1000, 2)))
    zones.sort(key=lambda z: -z["base_demand_ls"])
    for i, z in enumerate(zones):
        z["id"] = f"Z{i + 1}"
    return zones


class Distances:
    """Pipe-length distances: centre-to-centre between two pipes = shortest
    node distance + half of each pipe's length (the BattLeDIM rule)."""

    def __init__(self, wn):
        self.wn = wn
        G = nx.Graph()
        for n, l in wn.links():
            G.add_edge(l.start_node_name, l.end_node_name, weight=float(getattr(l, "length", 0.0) or 0.0))
        self.G = G
        self._c = {}

    def node(self, a, b):
        if a not in self._c:
            self._c[a] = nx.single_source_dijkstra_path_length(self.G, a, weight="weight")
        return self._c[a].get(b, np.inf)

    def _len(self, p):
        return float(getattr(self.wn.get_link(p), "length", 0.0) or 0.0)

    def pipe(self, p, q):
        if p == q:
            return 0.0
        lp, lq = self.wn.get_link(p), self.wn.get_link(q)
        m = min(self.node(a, b) for a in (lp.start_node_name, lp.end_node_name)
                for b in (lq.start_node_name, lq.end_node_name))
        return m + self._len(p) / 2 + self._len(q) / 2

    def pipe_node(self, p, n):
        lp = self.wn.get_link(p)
        return min(self.node(lp.start_node_name, n), self.node(lp.end_node_name, n)) + self._len(p) / 2
