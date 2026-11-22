// 4K README screenshots of the live control room and planner (1920x1080 layout at 2x pixel density).
import { chromium } from "playwright-core";
import path from "node:path";
const MON = "http://localhost:8050/job/ltownmonitor/files/dashboard.html";
const PLAN = "http://localhost:8050/job/eec1f1a9/files/plan.html";
const OUT = path.resolve("../../docs/img/4k");
const Y = 365, wait = (ms) => new Promise((r) => setTimeout(r, ms));
const setDay = (p, d) => p.evaluate((d) => { const s = document.getElementById("day"); s.value = d; s.dispatchEvent(new Event("input")); }, d);
const setLayer = (p, v) => p.evaluate((v) => { const s = document.getElementById("layer"); s.value = v; s.dispatchEvent(new Event("change")); }, v);
const pick = (p, d) => p.evaluate((d) => { const r = [...document.querySelectorAll(".alarm")].find((x) => x.innerText.includes(d)); if (r) r.click(); }, d);
const SHOTS = {
  "hero-3d": async (p) => { await p.goto(MON); await wait(2500); await setDay(p, Y + 110); await pick(p, "Apr 21"); await p.click("#v3d"); await wait(5000); },
  "control-room": async (p) => { await p.goto(MON); await wait(2500); await setDay(p, Y + 110); await pick(p, "Apr 21"); await wait(1500); },
  "answer-key-3d": async (p) => { await p.goto(MON); await wait(2500); await setDay(p, Y + 200); await p.check("#key"); await p.click("#v3d"); await wait(5000); },
  "pressure-management": async (p) => { await p.goto(MON); await wait(2500); await setDay(p, Y + 110); await setLayer(p, "drop"); await wait(2000); },
  "forecast": async (p) => { await p.goto(MON); await wait(2500); await setDay(p, Y + 111); await p.click("#t-fc"); await wait(2000); },
  "street-map": async (p) => { await p.goto(MON); await wait(2500); await setDay(p, Y + 200); await p.check("#key"); await p.click("#vst"); await wait(5000); },
  "sensor-planner": async (p) => { await p.goto(PLAN); await wait(3500); },
};
const want = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SHOTS);
const browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
for (const name of want) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await SHOTS[name](page);
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log("saved", name);
  await ctx.close();
}
await browser.close();
