// Records the AquaTwin UI shots for the demo film (1920x1080, Edge).
// Each shot is its own browser context, so each becomes one clean video file.
//   node record.mjs [shotName ...]
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const BASE = "http://localhost:8050";
const MON = `${BASE}/job/ltownmonitor/files/dashboard.html`;
const PLAN = `${BASE}/job/eec1f1a9/files/plan.html`;
const OUT = path.resolve("../film/assets/shots");
const RAW = path.resolve("raw");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(RAW, { recursive: true });
const W = 1920, H = 1080;
const Y = 365;            // the replay timeline starts 2018-01-01; alarms are reported from 2019
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function glide(page, x0, y0, x1, y1, ms, down = false) {
  const steps = Math.max(2, Math.round(ms / 16));
  await page.mouse.move(x0, y0);
  if (down) await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    const t = i / steps, e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    await page.mouse.move(x0 + (x1 - x0) * e, y0 + (y1 - y0) * e);
    await wait(ms / steps);
  }
  if (down) await page.mouse.up();
}
const setDay = (page, d) => page.evaluate((d) => { const s = document.getElementById("day"); s.value = d; s.dispatchEvent(new Event("input")); }, d);
const clickAlarmOnDay = (page, d) => page.evaluate((d) => {
  const rows = [...document.querySelectorAll(".alarm")]; const r = rows.find((x) => x.innerText.includes(d)); if (r) r.click();
}, d);
const setLayer = (page, v) => page.evaluate((v) => { const s = document.getElementById("layer"); s.value = v; s.dispatchEvent(new Event("change")); }, v);

const SHOTS = {
  // calm overview before any alarm: districts, loggers, street-map toggle
  async overview(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y); await wait(1500);
    await glide(page, 300, 300, 820, 520, 2600); await wait(600);
    await glide(page, 820, 520, 1000, 420, 1500); await wait(600);
    await page.click("#vst"); await wait(3500);
    await page.click("#v2d"); await wait(2500);
  },
  // control room replay: alarms arrive, charts step up
  async replay(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y + 6); await wait(1200);
    await page.click("#play"); await wait(17000);
    await page.click("#play"); await wait(1200);
  },
  // the biggest leak of the year: select, read, act
  async detail(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y + 110); await wait(700);
    await clickAlarmOnDay(page, "Apr 21"); await wait(2500);
    const crew = await page.$("#b-crew"); const b = await crew.boundingBox();
    await glide(page, 1200, 700, b.x + b.width / 2, b.y + b.height / 2, 900); await wait(400);
    await page.click("#b-crew"); await wait(1600);
    const v = await (await page.$("#b-valve")).boundingBox();
    await glide(page, b.x + b.width / 2, b.y + b.height / 2, v.x + v.width / 2, v.y + v.height / 2, 700); await wait(300);
    await page.click("#b-valve"); await wait(2600);
  },
  // plan -> 3D terrain, orbit
  async terrain(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y + 110); await clickAlarmOnDay(page, "Apr 21"); await wait(1200);
    await page.click("#v3d"); await wait(3200);
    const m = await (await page.$("#mapwrap")).boundingBox();
    const cx = m.x + m.width / 2, cy = m.y + m.height / 2;
    await glide(page, cx - 160, cy, cx + 220, cy - 30, 4200, true); await wait(800);
    await glide(page, cx + 100, cy, cx - 120, cy + 10, 3000, true); await wait(1500);
  },
  // answer key reveal while the year plays in 3D
  async answer(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y); await page.click("#v3d"); await wait(3000);
    await page.check("#key"); await wait(800);
    await page.click("#play"); await wait(15500);
    await page.click("#play"); await wait(1500);
  },
  // street-map view of the same network
  async street(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y + 200); await page.check("#key"); await wait(800);
    await page.click("#vst"); await wait(5500);
  },
  // smart pressure management + water quality layers
  async health(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y + 110); await wait(500);
    await setLayer(page, "drop"); await wait(4200);
    await page.click("#v3d"); await wait(3500);
    await setLayer(page, "chlorine"); await wait(4200);
    await setLayer(page, "age"); await wait(3500);
  },
  // day-ahead forecast: demand per district and tank T1, stepping through three days
  async forecast(page) {
    await page.goto(MON); await wait(2500);
    await setDay(page, Y + 110); await wait(400);
    await page.click("#t-fc"); await wait(3800);
    await page.evaluate(() => document.getElementById("fcpane").scrollTo({ top: 99999, behavior: "smooth" })); await wait(3200);
    for (let d = 111; d <= 113; d++) { await setDay(page, Y + d); await wait(1600); }
    await page.evaluate(() => document.getElementById("fcpane").scrollTo({ top: 0, behavior: "smooth" })); await wait(2500);
  },
  // sensor planner: coverage vs number of loggers, then 3D
  async planner(page) {
    await page.goto(PLAN); await wait(2500);
    const k = await (await page.$("#k")).boundingBox();
    await glide(page, k.x + k.width - 4, k.y + k.height / 2, k.x + k.width * 0.18, k.y + k.height / 2, 3500, true); await wait(800);
    await glide(page, k.x + k.width * 0.18, k.y + k.height / 2, k.x + k.width - 4, k.y + k.height / 2, 3000, true); await wait(700);
    await page.click("#v3d"); await wait(4500);
  },
  // any network: the upload app, then a different city opened in the control room
  async anycity(page) {
    await page.goto(BASE); await wait(2200);
    await page.click('[data-t="monitor"]'); await wait(2200);
    await page.click('[data-t="plan"]'); await wait(1200);
    await page.goto(MON); await wait(2200);
    await page.evaluate(async () => {
      const b = await fetch("/job/ltownmonitor/files/Net3.inp").then((r) => r.blob());
      const dt = new DataTransfer(); dt.items.add(new File([b], "Net3.inp"));
      const inp = document.getElementById("openfile"); inp.files = dt.files; inp.dispatchEvent(new Event("change"));
    });
    await wait(5000);
  },
};

const want = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SHOTS);
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
for (const name of want) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, recordVideo: { dir: RAW, size: { width: W, height: H } } });
  const page = await ctx.newPage();
  const t0 = Date.now();
  await SHOTS[name](page);
  const vid = page.video();
  await ctx.close();
  const webm = await vid.path();
  const mp4 = path.join(OUT, `${name}.mp4`);
  // trim the blank page-load second, encode H.264 at 30 fps
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "1.2", "-i", webm, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-an", mp4]);
  console.log(`${name}: ${((Date.now() - t0) / 1000).toFixed(1)} s -> ${mp4}`);
}
await browser.close();

