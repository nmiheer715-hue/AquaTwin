"""L-Town network helpers: districts (DMAs), pipe distances as used by the
official BattLeDIM scorer."""
import os

import networkx as nx
import numpy as np
import wntr

HERE = os.path.dirname(os.path.abspath(__file__))
INP = os.path.join(HERE, "raw", "L-TOWN.inp")
# set AQUATWIN_INP to use the calibrated twin (raw/L-TOWN_cal.inp)
MODEL_INP = os.environ.get("AQUATWIN_INP", INP)


def model(path=None):
    return wntr.network.WaterNetworkModel(path or MODEL_INP)


def districts(wn=None):
    """Node -> 'A' | 'B' | 'C'. Pipes only; PRVs and the pump are the
    district boundaries (A: fed by the reservoirs through PRV-1/2;
    B: behind PRV-3; C: fed by tank T1)."""
    wn = wn or model()
    G = nx.Graph()
    for _, l in wn.links():
        if l.link_type == "Pipe":
            G.add_edge(l.start_node_name, l.end_node_name)
    area = {}
    for comp in nx.connected_components(G):
        if "T1" in comp:
            a = "C"
        elif "n226" in comp:
            a = "B"
        else:
            a = "A"
        for n in comp:
            area[n] = a
    return area


def pipe_areas(wn=None):
    wn = wn or model()
    na = districts(wn)
    return {n: na[l.start_node_name] for n, l in wn.links() if l.link_type == "Pipe"}


class Distances:
    """Pipe-length distances (official rule: centre-to-centre distance
    between two pipes = shortest node distance + half of each length)."""

    def __init__(self, wn=None):
        self.wn = wn or model()
        G = nx.Graph()
        for n, l in self.wn.links():
            G.add_edge(l.start_node_name, l.end_node_name,
                       weight=float(getattr(l, "length", 0.0) or 0.0))
        self.G = G
        self._cache = {}

    def node(self, a, b):
        if a not in self._cache:
            self._cache[a] = nx.single_source_dijkstra_path_length(self.G, a, weight="weight")
        return self._cache[a].get(b, np.inf)

    def pipe(self, p, q):
        if p == q:
            return 0.0
        lp, lq = self.wn.get_link(p), self.wn.get_link(q)
        ends = [(a, b) for a in (lp.start_node_name, lp.end_node_name)
                for b in (lq.start_node_name, lq.end_node_name)]
        m = min(self.node(a, b) for a, b in ends)
        return m + float(getattr(lp, "length", 0.0) or 0) / 2 + float(getattr(lq, "length", 0.0) or 0) / 2

    def pipe_node(self, p, n):
        lp = self.wn.get_link(p)
        return min(self.node(lp.start_node_name, n), self.node(lp.end_node_name, n)) + \
            float(getattr(lp, "length", 0.0) or 0) / 2
