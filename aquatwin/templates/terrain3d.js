/* AquaTwin 3D terrain view, shared by the control room and the sensor plan.
   Draws any network in perspective at its real ground elevations.
   geo: { W, H, zones:[{id,color,segs:[x1,y1,z1,x2,y2,z2,...]}], sources:{id:[x,y,z]} }
   markers: { sensors:[[x,y,z]], columns:[{id,p,h,color,pulse,wide}], rings:[{p,color,opacity}],
              crosses:[{p,color}], boxes:[{p,color}] } */
function Terrain3D(opt) {
  if (!window.THREE) return null;
  const T = THREE, cv = opt.canvas, wrap = opt.wrap, hint = opt.hint;
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const renderer = new T.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  const scene = new T.Scene(), cam = new T.PerspectiveCamera(38, 1, 1, 20000);
  let geo = null, W = 1000, H = 1000, cx = 500, cy = 500;
  const V = (p) => new T.Vector3(p[0] - cx, p[2] || 0, p[1] - cy);
  const netG = new T.Group(), dynG = new T.Group(), colG = new T.Group();
  scene.add(netG, dynG, colG);

  const core = new T.CylinderGeometry(3.2, 3.2, 1, 14); core.translate(0, 0.5, 0);
  const halo = new T.CylinderGeometry(9, 9, 1, 20, 1, true); halo.translate(0, 0.5, 0);
  const disc = new T.RingGeometry(5, 9, 28); disc.rotateX(-Math.PI / 2);
  const ring = new T.RingGeometry(9, 11, 36); ring.rotateX(-Math.PI / 2);
  const sphere = new T.SphereGeometry(4, 12, 8), box = new T.BoxGeometry(12, 12, 12);
  const cols = new Map(), pickable = [];
  let animateNew = false;

  // pipeColor: null = district colours, or a function (x, y) -> "#rrggbb" | null giving each
  // pipe end its colour from a data layer (pressure saving, water age, chlorine)
  let pipeColor = null;
  function drawPipes() {
    netG.children.filter((o) => o.userData.pipes).forEach((o) => netG.remove(o));
    const c = new T.Color();
    geo.zones.forEach((z) => {
      const s = z.segs || [], n = s.length / 3, a = new Float32Array(s.length), col = new Float32Array(s.length);
      for (let i = 0; i < n; i++) {
        a[i * 3] = s[i * 3] - cx; a[i * 3 + 1] = s[i * 3 + 2]; a[i * 3 + 2] = s[i * 3 + 1] - cy;
        c.set((pipeColor && pipeColor(s[i * 3], s[i * 3 + 1])) || (pipeColor ? "#33414f" : z.color));
        col.set([c.r, c.g, c.b], i * 3);
      }
      const bg = new T.BufferGeometry(); bg.setAttribute("position", new T.BufferAttribute(a, 3)); bg.setAttribute("color", new T.BufferAttribute(col, 3));
      const ls = new T.LineSegments(bg, new T.LineBasicMaterial({ vertexColors: true })); ls.userData.pipes = true; netG.add(ls);
    });
    kick();
  }
  function setPipeColor(fn) { pipeColor = fn; drawPipes(); }
  const dotTex = (() => {                                   // round, soft-edged dot for data points
    const cv2 = document.createElement("canvas"); cv2.width = cv2.height = 64; const g2 = cv2.getContext("2d");
    g2.beginPath(); g2.arc(32, 32, 26, 0, Math.PI * 2); g2.fillStyle = "#fff"; g2.fill();
    g2.lineWidth = 6; g2.strokeStyle = "rgba(11,18,25,.9)"; g2.stroke();
    return new T.CanvasTexture(cv2);
  })();

  function setGeo(g) {
    geo = g; W = g.W; H = g.H; cx = W / 2; cy = H / 2;
    netG.clear();
    const grid = new T.GridHelper(Math.max(W, H) * 1.25, 28, 0x213041, 0x15212d); grid.position.y = -2; netG.add(grid);
    pipeColor = null; drawPipes();
    const bm = new T.MeshBasicMaterial({ color: 0xdde6ee });
    Object.values(g.sources || {}).forEach((p) => { const m = new T.Mesh(box, bm); m.position.copy(V(p)); m.position.y += 6; netG.add(m); });
    for (const c of cols.values()) colG.remove(c.g);
    cols.clear(); pickable.length = 0;
    if (active) { orb.r = fit(); }
    kick();
  }

  function setMarkers(mk) {
    dynG.clear();
    const sm = new T.MeshBasicMaterial({ color: 0x5ec8dc });
    (mk.sensors || []).forEach((p) => { const m = new T.Mesh(sphere, sm); m.position.copy(V(p)); dynG.add(m); });
    if (mk.dots && mk.dots.length) {                       // coloured junction dots (a data layer)
      const pos = new Float32Array(mk.dots.length * 3), colr = new Float32Array(mk.dots.length * 3), c = new T.Color();
      mk.dots.forEach((d, i) => { const v = V(d.p); pos.set([v.x, v.y + 1.5, v.z], i * 3); c.set(d.color); colr.set([c.r, c.g, c.b], i * 3); });
      const bg = new T.BufferGeometry(); bg.setAttribute("position", new T.BufferAttribute(pos, 3)); bg.setAttribute("color", new T.BufferAttribute(colr, 3));
      dynG.add(new T.Points(bg, new T.PointsMaterial({ size: 13, vertexColors: true, sizeAttenuation: true, map: dotTex, alphaTest: 0.5, transparent: true })));
    }
    (mk.boxes || []).forEach((b) => {
      const m = new T.Mesh(new T.OctahedronGeometry(7), new T.MeshBasicMaterial({ color: b.color })); m.position.copy(V(b.p)); m.position.y += 8; dynG.add(m);
    });
    (mk.rings || []).forEach((r) => {
      const m = new T.Mesh(ring, new T.MeshBasicMaterial({ color: r.color, transparent: true, opacity: r.opacity ?? 0.7, side: T.DoubleSide }));
      m.position.copy(V(r.p)); m.position.y += 0.8; dynG.add(m);
    });
    (mk.crosses || []).forEach((c) => {
      const mat = new T.MeshBasicMaterial({ color: c.color });
      [Math.PI / 4, -Math.PI / 4].forEach((r) => { const m = new T.Mesh(new T.BoxGeometry(18, 2.5, 3), mat); m.position.copy(V(c.p)); m.position.y += 2; m.rotation.y = r; dynG.add(m); });
    });
    // columns keep their identity so new ones can grow out of the pipe
    const want = new Set((mk.columns || []).map((c) => c.id));
    for (const [id, c] of cols) if (!want.has(id)) { colG.remove(c.g); pickable.splice(pickable.indexOf(c.mc), 1); cols.delete(id); }
    (mk.columns || []).forEach((c) => {
      let o = cols.get(c.id);
      if (!o) {
        const g = new T.Group();
        const mc = new T.Mesh(core, new T.MeshBasicMaterial({ color: c.color, transparent: true, opacity: 0.95 }));
        const mh = new T.Mesh(halo, new T.MeshBasicMaterial({ color: c.color, transparent: true, opacity: 0.14, side: T.DoubleSide, depthWrite: false }));
        const md = new T.Mesh(disc, new T.MeshBasicMaterial({ color: c.color, transparent: true, opacity: 0.7, side: T.DoubleSide }));
        md.position.y = 0.6; mc.userData.id = c.id; g.add(mc, mh, md); colG.add(g); pickable.push(mc);
        o = { g, mc, mh, md, born: animateNew && active && !REDUCED ? performance.now() : -1e9 };
        cols.set(c.id, o);
      }
      o.g.position.copy(V(c.p)); o.h = c.h; o.pulse = c.pulse && !REDUCED;
      [o.mc, o.mh, o.md].forEach((m) => m.material.color.set(c.color));
      o.g.scale.x = o.g.scale.z = c.wide ? 1.5 : 1;
    });
    animateNew = true;
    kick();
  }

  // camera: orbit around the network centre; phi 0 = straight down (matches the plan view)
  const orb = { r: 1000, phi: 0.0001, theta: 0 }; let tween = null, active = false, raf = 0;
  function fit() { const t = Math.tan((cam.fov * Math.PI) / 360); return (Math.max(H, W / cam.aspect) / 2 / t) * 1.06; }
  function place() {
    const { r, phi, theta } = orb;
    cam.position.set(r * Math.sin(phi) * Math.sin(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.cos(theta));
    cam.lookAt(0, 20, 0);
  }
  function go(to, ms, done) {
    if (REDUCED || !ms) { Object.assign(orb, to); place(); done && done(); kick(); return; }
    tween = { from: { ...orb }, to, t0: performance.now(), ms, done }; kick();
  }
  function frame(now) {
    raf = 0;
    if (tween) {
      const k = Math.min(1, (now - tween.t0) / tween.ms), e = ease(k);
      for (const key in tween.to) orb[key] = tween.from[key] + (tween.to[key] - tween.from[key]) * e;
      if (k >= 1) { const d = tween.done; tween = null; d && d(); }
    }
    place();
    let more = !!tween;
    for (const c of cols.values()) {
      const g = Math.min(1, (now - c.born) / 700);
      c.mc.scale.y = c.mh.scale.y = Math.max(0.01, c.h * (1 - Math.pow(1 - g, 3)));
      if (g < 1) more = true;
      c.mh.material.opacity = c.pulse ? 0.12 + 0.1 * (0.5 + 0.5 * Math.sin(now / 260)) : 0.1;
      if (c.pulse) more = true;
    }
    renderer.render(scene, cam);
    if (active && more) raf = requestAnimationFrame(frame);
  }
  function kick() { if (active && !raf) raf = requestAnimationFrame(frame); }
  function resize() {
    const w = wrap.clientWidth, h = wrap.clientHeight; if (!w || !h) return;
    renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix(); kick();
  }
  new ResizeObserver(resize).observe(wrap);

  let drag = null;
  cv.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, moved: 0, phi: orb.phi, theta: orb.theta }; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener("pointermove", (e) => {
    if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved = Math.max(drag.moved, Math.abs(dx) + Math.abs(dy));
    orb.theta = drag.theta - dx * 0.006; orb.phi = Math.min(1.35, Math.max(0.0001, drag.phi - dy * 0.006)); kick();
  });
  cv.addEventListener("pointerup", (e) => {
    if (drag && drag.moved < 5 && opt.onPick) {
      const r = cv.getBoundingClientRect(), m = new T.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      const rc = new T.Raycaster(); rc.setFromCamera(m, cam);
      const hit = rc.intersectObjects(pickable)[0]; if (hit) opt.onPick(hit.object.userData.id);
    }
    drag = null;
  });
  cv.addEventListener("wheel", (e) => { e.preventDefault(); orb.r = Math.min(fit() * 2.5, Math.max(fit() * 0.2, orb.r * (1 + Math.sign(e.deltaY) * 0.1))); kick(); }, { passive: false });

  setGeo(opt.geo);
  return {
    setGeo, setMarkers, setPipeColor,
    enter() {
      active = true; resize(); orb.r = fit(); orb.phi = 0.0001; orb.theta = 0; place();
      wrap.classList.add("is3d"); cv.classList.add("on"); if (hint) hint.hidden = false; kick();
      // cross-fade from the plan into an identical top-down camera, then tilt into perspective
      setTimeout(() => go({ phi: 0.92, theta: -0.38, r: fit() * 1.28 }, 1100), REDUCED ? 0 : 380);
    },
    exit() {
      go({ phi: 0.0001, theta: 0, r: fit() }, 700, () => {
        wrap.classList.remove("is3d"); cv.classList.remove("on"); if (hint) hint.hidden = true;
        setTimeout(() => { active = false; }, 400);
      });
    },
    get on() { return active; },
  };
}
