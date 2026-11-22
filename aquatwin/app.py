"""AquaTwin local web app: upload a city's pipe network and run on it.

    python -m aquatwin.app            then open http://127.0.0.1:8050

Two flows:
  Plan sensors   upload the network (.inp) only -> proposed zones, ranked logger
                 locations and coverage
  Monitor leaks  upload the network + SCADA CSVs -> zones, thresholds, alarms
                 and the control room

Runs locally only (127.0.0.1); files stay on this computer.
"""
import json
import os
import shutil
import threading
import traceback
import uuid
from datetime import datetime

from flask import Flask, abort, jsonify, redirect, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JOBS = os.path.join(ROOT, "aquatwin_jobs")
SAMPLE = os.path.join(ROOT, "battledim", "raw")
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024     # 1 GB of SCADA is plenty
STATE = {}


def sniff_csv(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        head, row = f.readline(), f.readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    decimal = "," if sep == ";" and "," in row else "."
    return dict(sep=sep, decimal=decimal)


def save_files(field, folder):
    out = []
    for f in request.files.getlist(field):
        if f and f.filename:
            name = os.path.basename(f.filename).replace(" ", "_")
            p = os.path.join(folder, f"{field}_{len(out)}_{name}")
            f.save(p)
            out.append(p)
    return out


def start(job, spec):
    """Run the job in its own Python process (aquatwin.worker)."""
    import subprocess
    import sys
    d = os.path.join(JOBS, job)
    json.dump(spec, open(os.path.join(d, "job.json"), "w"), indent=1)
    json.dump(dict(status="running", result=None), open(os.path.join(d, "status.json"), "w"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([sys.executable, "-m", "aquatwin.worker", d], cwd=ROOT, creationflags=flags)
    STATE[job] = True


@app.get("/")
def home():
    return PAGE_HOME


@app.post("/plan")
def plan_job():
    job = uuid.uuid4().hex[:8]
    d = os.path.join(JOBS, job)
    os.makedirs(d)
    if request.form.get("sample") == "1":
        inp = os.path.join(d, "L-TOWN.inp")
        shutil.copy(os.path.join(SAMPLE, "L-TOWN.inp"), inp)
        name = "L-Town (sample)"
    else:
        files = save_files("inp", d)
        if not files:
            return "Choose an EPANET .inp file.", 400
        inp, name = files[0], request.form.get("name") or "My network"
    k = int(request.form.get("loggers") or 0)
    existing = [s.strip() for s in (request.form.get("existing") or "").replace("\n", ",").split(",") if s.strip()]
    start(job, dict(kind="plan", inp=inp, name=name, loggers=k, existing=existing,
                    max_zone_junctions=int(request.form.get("max_zone") or 300)))
    return redirect(f"/job/{job}")


@app.post("/monitor")
def monitor_job():
    job = uuid.uuid4().hex[:8]
    d = os.path.join(JOBS, job)
    os.makedirs(d)
    f = request.form
    if f.get("sample") == "1":
        cfg = dict(name="L-Town (sample)", inp=os.path.join(SAMPLE, "L-TOWN.inp"), csv=dict(sep=";", decimal=","),
                   pressures=[os.path.join(SAMPLE, f"{y}_SCADA_Pressures.csv") for y in (2018, 2019)],
                   flows=[os.path.join(SAMPLE, f"{y}_SCADA_Flows.csv") for y in (2018, 2019)],
                   levels=[os.path.join(SAMPLE, f"{y}_SCADA_Levels.csv") for y in (2018, 2019)],
                   amr=[os.path.join(SAMPLE, f"{y}_SCADA_Demands.csv") for y in (2018, 2019)],
                   flow_units="m3/h", amr_units="L/h", pattern_period="day_of_year",
                   report_from="2019-01-01", history_days=7, k_sigma=4.0,
                   repairs=os.path.join(ROOT, "examples", "ltown_repairs_2018.csv"),
                   currency="€", cost_per_m3=0.8, false_alarm_cost=500)
        truth = os.path.join(ROOT, "battledim", "truth_2019.csv")
    else:
        inp = save_files("inp", d)
        pres, flows = save_files("pressures", d), save_files("flows", d)
        if not inp or not pres or not flows:
            return "The network (.inp), at least one pressure CSV and one flow CSV are required.", 400
        cfg = dict(name=f.get("name") or "My network", inp=inp[0], csv=sniff_csv(pres[0]),
                   pressures=pres, flows=flows, levels=save_files("levels", d), amr=save_files("amr", d),
                   flow_units=f.get("flow_units", "m3/h"), amr_units=f.get("amr_units", "L/h"),
                   pattern_period=f.get("pattern_period", "calendar"),
                   history_days=int(f.get("history_days") or 7), k_sigma=float(f.get("k_sigma") or 4.0),
                   report_from=f.get("report_from") or None)
        t = save_files("truth", d)
        truth = t[0] if t else None
    cfg["outdir"] = d
    json.dump(cfg, open(os.path.join(d, "config.json"), "w"), indent=1)
    start(job, dict(kind="monitor", truth=truth if truth and os.path.exists(truth) else None))
    return redirect(f"/job/{job}")


def job_dir(job):
    d = os.path.join(JOBS, os.path.basename(job))
    if not os.path.isfile(os.path.join(d, "status.json")):
        abort(404)
    return d


@app.get("/job/<job>")
def job_page(job):
    job_dir(job)
    return PAGE_JOB.replace("__JOB__", job)


@app.get("/job/<job>/status")
def job_status(job):
    d = job_dir(job)
    st = json.load(open(os.path.join(d, "status.json")))
    lp = os.path.join(d, "log.txt")
    st["log"] = open(lp, encoding="utf-8").read().splitlines() if os.path.exists(lp) else []
    return jsonify(st)


@app.get("/job/<job>/files/<path:name>")
def job_file(job, name):
    return send_from_directory(os.path.join(JOBS, job), name)


STYLE = """
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600&display=swap">
<style>
:root{color-scheme:dark;--bg:#0b1219;--panel:#101a24;--raise:#15212d;--line:#213041;--fg:#dde6ee;--muted:#8597a8;--accent:#5ec8dc;--ok:#45b383;--crit:#e5574e;
--sans:"IBM Plex Sans",system-ui,"Segoe UI",sans-serif;--cond:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box} [hidden]{display:none!important} body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 var(--sans)}
.wrap{max-width:980px;margin:0 auto;padding:28px max(16px,env(safe-area-inset-right,0px)) 40px max(16px,env(safe-area-inset-left,0px))}
h1{font:600 28px var(--cond);margin:0 0 4px} .lede{color:var(--muted);margin:0 0 22px;max-width:68ch}
.tabs{display:flex;gap:6px;margin-bottom:-1px} .tab{padding:9px 16px;border:1px solid var(--line);border-bottom:none;border-radius:8px 8px 0 0;background:var(--panel);color:var(--muted);cursor:pointer;font:500 14px var(--sans)}
.tab[aria-selected=true]{background:var(--raise);color:var(--fg)}
form{background:var(--raise);border:1px solid var(--line);border-radius:0 8px 8px 8px;padding:20px;display:grid;gap:16px}
.row{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
label{display:flex;flex-direction:column;gap:6px;color:var(--muted);font-size:12.5px}
label b{color:var(--fg);font-weight:500;font-size:13.5px}
input,select,textarea{font:13px var(--sans);color:var(--fg);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px}
input[type=file]{padding:6px}
button{font:600 14px var(--sans);background:var(--accent);color:#062029;border:0;border-radius:6px;padding:10px 18px;cursor:pointer;justify-self:start}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
button:focus-visible,input:focus-visible,select:focus-visible,.tab:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hint{color:var(--muted);font-size:12px;margin:0} code{font-family:var(--mono);font-size:12px;color:var(--fg)}
.actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.log{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;font:12.5px/1.6 var(--mono);white-space:pre-wrap;max-height:60vh;overflow:auto}
.st{display:inline-block;padding:2px 8px;border-radius:4px;font:600 11px var(--sans);text-transform:uppercase;letter-spacing:.06em}
.running{background:rgba(94,200,220,.15);color:var(--accent)} .done{background:rgba(69,179,131,.15);color:var(--ok)} .failed{background:rgba(229,87,78,.15);color:var(--crit)}
a{color:var(--accent)}
</style>"""

PAGE_HOME = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AquaTwin</title>""" + STYLE + """</head><body><div class="wrap">
<h1>AquaTwin</h1>
<p class="lede">Upload the water pipe network of a city or area. Start with the network alone to plan where loggers should go,
or add the utility's SCADA readings to monitor leaks.</p>
<div class="tabs" role="tablist">
 <button class="tab" role="tab" aria-selected="true" data-t="plan">Plan sensors</button>
 <button class="tab" role="tab" aria-selected="false" data-t="monitor">Monitor leaks</button>
</div>

<form id="plan" action="/plan" method="post" enctype="multipart/form-data">
 <div class="row">
  <label><b>Network model (.inp)</b><input type="file" name="inp" accept=".inp"></label>
  <label><b>Network name</b><input name="name" placeholder="e.g. Ward 12, Pune"></label>
  <label><b>Loggers to place</b><input type="number" name="loggers" min="1" max="200" placeholder="default: 1 per 30 pipes"></label>
 </div>
 <div class="row">
  <label><b>Existing pressure loggers (optional)</b><textarea name="existing" rows="2" placeholder="Junction IDs from the model, separated by commas"></textarea></label>
  <label><b>Largest zone (junctions)</b><input type="number" name="max_zone" min="10" value="300">
   <span class="hint">Bigger zones are split by new boundary meters</span></label>
 </div>
 <p class="hint">The model must be an EPANET input file with node coordinates. Export it from EPANET, WaterGEMS, InfoWater or your GIS.
 Planning a 1,000-junction network takes a few minutes.</p>
 <div class="actions"><button type="submit">Plan sensors</button>
  <button class="ghost" type="submit" name="sample" value="1">Use the L-Town sample</button></div>
</form>

<form id="monitor" action="/monitor" method="post" enctype="multipart/form-data" hidden>
 <div class="row">
  <label><b>Network model (.inp)</b><input type="file" name="inp" accept=".inp"></label>
  <label><b>Network name</b><input name="name" placeholder="e.g. Ward 12, Pune"></label>
 </div>
 <div class="row">
  <label><b>Pressures CSV</b><input type="file" name="pressures" accept=".csv" multiple></label>
  <label><b>Flows CSV</b><input type="file" name="flows" accept=".csv" multiple></label>
  <label><b>Tank levels CSV (optional)</b><input type="file" name="levels" accept=".csv" multiple></label>
  <label><b>Smart meters CSV (optional)</b><input type="file" name="amr" accept=".csv" multiple></label>
 </div>
 <p class="hint">Each CSV: first column a timestamp, then one column per sensor named with its EPANET ID
 (node ID for pressures, levels and smart meters; link ID for flows). Flow is positive in the link's EPANET direction.
 Several files per kind (e.g. one per year) are joined.</p>
 <div class="row">
  <label><b>Flow units</b><select name="flow_units"><option>m3/h</option><option>L/s</option><option>m3/s</option></select></label>
  <label><b>Smart meter units</b><select name="amr_units"><option>L/h</option><option>m3/h</option><option>L/s</option></select></label>
  <label><b>Weekly pattern</b><select name="pattern_period"><option value="calendar">Calendar weekdays</option><option value="day_of_year">Restarts every 1 January</option></select></label>
  <label><b>Alarm threshold (× noise)</b><input type="number" name="k_sigma" step="0.5" min="1" value="4"></label>
  <label><b>Leak-free start (days)</b><input type="number" name="history_days" min="3" value="7"></label>
  <label><b>Report alarms from (optional)</b><input type="date" name="report_from"></label>
 </div>
 <label><b>Known leaks CSV for evaluation (optional)</b><input type="file" name="truth" accept=".csv">
 <span class="hint">Columns: link_id, start, end. Only used to score the alarms.</span></label>
 <div class="actions"><button type="submit">Run monitoring</button>
  <button class="ghost" type="submit" name="sample" value="1">Use the L-Town sample</button></div>
</form>
</div>
<script>
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{document.querySelectorAll(".tab").forEach(x=>x.setAttribute("aria-selected",x===t));
 document.getElementById("plan").hidden=t.dataset.t!=="plan";document.getElementById("monitor").hidden=t.dataset.t!=="monitor"});
</script></body></html>"""

PAGE_JOB = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AquaTwin run</title>""" + STYLE + """</head><body><div class="wrap">
<h1>AquaTwin run <span id="st" class="st running">running</span></h1>
<p class="lede" id="msg">Working on the network. This page updates by itself.</p>
<div class="actions" id="open" hidden><a id="link" href="#"><button type="button">Open results</button></a> <a href="/">Start another run</a></div>
<h2 style="font:600 13px var(--sans);color:var(--muted);margin:22px 0 8px">Progress</h2>
<div class="log" id="log"></div></div>
<script>
const job="__JOB__";
async function tick(){const r=await fetch(`/job/${job}/status`);const s=await r.json();
 document.getElementById("log").textContent=s.log.join("\\n");const st=document.getElementById("st");st.textContent=s.status;st.className="st "+s.status;
 if(s.status==="done"){document.getElementById("msg").textContent="Finished.";document.getElementById("open").hidden=false;document.getElementById("link").href=`/job/${job}/files/${s.result.page}`;return}
 if(s.status==="failed"){document.getElementById("msg").textContent="The run stopped. The last lines below say why.";return}
 setTimeout(tick,1500)}
tick();
</script></body></html>"""


if __name__ == "__main__":
    os.makedirs(JOBS, exist_ok=True)
    app.run(host="127.0.0.1", port=8050, debug=False)
