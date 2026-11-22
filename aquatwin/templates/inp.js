/* Reads an EPANET .inp file in the browser and returns a drawable network:
   { geo: {W,H,zones,sources}, stats } in the same shape the Python export uses.
   Zones: parts of the network separated by pumps and valves (natural districts). */
const AQ_PALETTE = ["#557390", "#63a27f", "#b08b5c", "#8a6fb0", "#b0606b", "#5e9fa8", "#a39a4f", "#7d8796"];

function parseInp(text, name) {
  const sec = {}; let cur = null;
  for (let line of text.split(/\r?\n/)) {
    const c = line.indexOf(";"); if (c >= 0) line = line.slice(0, c);
    line = line.trim(); if (!line) continue;
    if (line[0] === "[") { cur = line.toUpperCase(); sec[cur] = sec[cur] || []; continue; }
    if (cur) sec[cur].push(line.split(/\s+/));
  }
  if (!sec["[PIPES]"] && !sec["[JUNCTIONS]"]) throw new Error("This does not look like an EPANET .inp file: it has no [JUNCTIONS] or [PIPES] section.");
  const elev = {}, kind = {};
  (sec["[JUNCTIONS]"] || []).forEach((r) => { elev[r[0]] = +r[1] || 0; kind[r[0]] = "J"; });
  (sec["[RESERVOIRS]"] || []).forEach((r) => { elev[r[0]] = +r[1] || 0; kind[r[0]] = "R"; });
  (sec["[TANKS]"] || []).forEach((r) => { elev[r[0]] = +r[1] || 0; kind[r[0]] = "T"; });
  const xy = {};
  (sec["[COORDINATES]"] || []).forEach((r) => { if (r.length >= 3) xy[r[0]] = [+r[1], +r[2]]; });
  if (!Object.keys(xy).length) throw new Error("This file has no [COORDINATES] section, so the network cannot be drawn. Export it again with node coordinates.");
  const links = [];
  [["[PIPES]", "pipe"], ["[PUMPS]", "pump"], ["[VALVES]", "valve"]].forEach(([s, t]) =>
    (sec[s] || []).forEach((r) => { if (xy[r[1]] && xy[r[2]]) links.push({ id: r[0], a: r[1], b: r[2], t }); }));

  const xs = Object.values(xy).map((p) => p[0]), ys = Object.values(xy).map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const W = 1000, H = Math.min(1400, Math.max(300, (W * (y1 - y0 || 1)) / (x1 - x0 || 1)));
  const ev = Object.keys(xy).map((n) => elev[n] ?? 0), e0 = Math.min(...ev), e1 = Math.max(...ev);
  const P = (n) => [+(((xy[n][0] - x0) / (x1 - x0 || 1)) * W).toFixed(1), +(((y1 - xy[n][1]) / (y1 - y0 || 1)) * H).toFixed(1),
    e1 > e0 ? +((((elev[n] ?? e0) - e0) / (e1 - e0)) * 80).toFixed(1) : 0];

  // natural districts: union-find over pipes only (pumps and valves separate them)
  const parent = {}; const find = (n) => (parent[n] === undefined ? n : (parent[n] = find(parent[n])));
  links.filter((l) => l.t === "pipe").forEach((l) => { const a = find(l.a), b = find(l.b); if (a !== b) parent[a] = b; });
  const sizes = {}; Object.keys(kind).forEach((n) => { if (kind[n] === "J") { const r = find(n); sizes[r] = (sizes[r] || 0) + 1; } });
  const order = Object.keys(sizes).sort((a, b) => sizes[b] - sizes[a]);
  const zid = {}; order.forEach((r, i) => (zid[r] = sizes[r] >= 5 ? "Z" + (i + 1) : "other"));
  const groups = {};
  links.forEach((l) => {
    const z = zid[find(l.a)] || zid[find(l.b)] || "other", a = P(l.a), b = P(l.b);
    const g = groups[z] || (groups[z] = { path: [], segs: [] });
    g.path.push(`M${a[0]} ${a[1]}L${b[0]} ${b[1]}`); g.segs.push(a[0], a[1], a[2], b[0], b[1], b[2]);
  });
  const zones = Object.keys(groups).sort((a, b) => (a === "other") - (b === "other") || (+a.slice(1)) - (+b.slice(1)))
    .map((z, i) => ({ id: z, color: z === "other" ? "#3a4652" : AQ_PALETTE[i % AQ_PALETTE.length], path: groups[z].path.join(""), segs: groups[z].segs,
      label: z === "other" ? "Small parts / transmission" : `${z} · ${sizes[order.find((r) => zid[r] === z)]} junctions` }));
  const sources = {};
  Object.keys(kind).forEach((n) => { if ((kind[n] === "R" || kind[n] === "T") && xy[n]) sources[n] = P(n); });
  const count = (t) => links.filter((l) => l.t === t).length;
  return {
    geo: { W, H: +H.toFixed(1), zones, sources },
    stats: { name, junctions: Object.values(kind).filter((k) => k === "J").length, pipes: count("pipe"), pumps: count("pump"),
      valves: count("valve"), reservoirs: Object.values(kind).filter((k) => k === "R").length, tanks: Object.values(kind).filter((k) => k === "T").length,
      districts: zones.filter((z) => z.id !== "other").length, elev: [e0, e1] },
  };
}
