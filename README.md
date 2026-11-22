# AquaTwin: AI leak detection and automatic isolation for city water networks

**i-Hack 2026 (E-Summit, IIT Bombay) · TIH Physical AI Hackathon · Track 4: AI in Water Management**

AquaTwin watches a city water network through a small number of pressure loggers and
the supply meters a utility already has. A hydraulic digital twin runs alongside it.
When the readings drift away from what the twin expects, the AI raises an alarm, ranks
the most likely leak locations, and closes motorised valves around the leak, all within
about an hour and a half of the pipe failing. Today, leaks in Indian cities often run for days
before someone reports them.

```
SENSE    pressure loggers (10) + supply/tank meters + large-customer smart meters
DECIDE   digital twin -> calibrated residuals -> leak alarm -> AI ranks leak locations
ACT      motorised isolation valves close around the leak; crew gets a 5-node search zone
```

## How it works

| Stage | What happens | Why it is built this way |
|---|---|---|
| Digital twin | EPANET model of the network, run with WNTR, fed with the pump schedule SCADA records | Same model-based approach as Global Omnium (Valencia) and DC Water |
| Water balance | Total supply = source meters + tank level change. Every litre lost shows up | Tanks hide leaks from inlet meters alone; utilities close the balance with level sensors |
| Calibration | Domestic demand level re-fitted every 15 min from the last 8 h; large customers read from smart meters | Removes normal day-to-day demand swings so they are not mistaken for leaks |
| Detection | Step-change alarm on unexplained supply rise and pressure drop | A leak starts suddenly; model error drifts slowly |
| Localisation | Hybrid: ExtraTrees classifier + physics match to each node's leak signature | ML learns from simulated history; physics generalises to unseen cases |
| Sensor placement | Greedy optimisation on the twin | Gets the most information from a fixed sensor budget |
| Response | Motorised valves isolate the predicted node; acoustic crew pinpoints inside the top-5 zone if needed | Mirrors the AI-narrows-then-acoustic-pinpoints workflow used by Thames Water |

## Results

**International benchmark (BattLeDIM 2020, L-Town):** with the 4σ low-false-alarm setting,
15 of 23 leaks found in the 2019 evaluation year with 6 false alarms, economic score
€303,324 under the official scoring rules (2020 joint winners: €260k to €265k, submitted
blind). The 2.5σ setting selected on 2018 alone finds 18 of 23 with 13 false alarms
(€343,806). The 4σ choice was made after seeing 2019 results. See
[battledim/](battledim/) and the fair-comparison note in [CONCEPT_NOTE.md](CONCEPT_NOTE.md).

**Controlled simulation (Net3, 2,000 leaks):** see `results/metrics.json`,
`results/isolation.json` and `figures/`.

### BattLeDIM pipeline (`battledim/`)

```bash
cd battledim
../.venv/Scripts/python.exe load.py          # cache the SCADA CSVs (data in battledim/raw from Zenodo 4017659)
../.venv/Scripts/python.exe sensitivity.py   # leak signature of every node from the L-Town twin (~1 min)
../.venv/Scripts/python.exe submit.py        # run 2018-2019 day by day, write submission, score
../.venv/Scripts/python.exe figures.py       # map, 2019 signals, leaderboard chart
```

| File | Purpose |
|---|---|
| `network.py` | Districts (DMAs) and official pipe-distance rule |
| `signals.py` | Minimum night flow (A+B) and smart-meter water balance (C) |
| `sensitivity.py` | Twin leak signatures at 03:00 for all 769 nodes |
| `detect.py` | Causal day-by-day detection, repair tracking, localisation |
| `scoring.py` | Python port of the official KIOS scoring algorithm (matches the official perfect score exactly) |
| `submit.py` | Writes `submission/AquaTwin.txt` and `results/battledim_score.json` |
| `sweep.py` | Settings selection on 2018 only (A: year-end pursuit, B: localisation sweep, C: low-false-alarm search) |

## Use it on your own network

AquaTwin runs on any EPANET network. Start the local app and upload a city's pipe network:

```bash
.venv/Scripts/python.exe -m aquatwin.app      # then open http://127.0.0.1:8050
```

- **Plan sensors** (network only): proposed district metered areas, extra boundary meters
  where zones are too big, ranked pressure-logger locations and a coverage curve.
- **Monitor leaks** (network + SCADA CSVs): zones and indicators set up automatically,
  thresholds learned from the data, daily alarms with zone, size and suspected pipe, and the
  control room.

See [ONBOARDING.md](ONBOARDING.md) for the data format and what to expect.

## Run the research pipelines

Python 3.12. From this folder:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe wntr six scikit-learn matplotlib pandas networkx scipy
.venv/Scripts/python.exe generate.py 2000 300   # simulate 2,000 leaks + 300 normal days (~20 min, 8 cores)
.venv/Scripts/python.exe train.py               # sensor placement, detector, localisation AI
.venv/Scripts/python.exe isolate.py             # valve isolation and water-saved study
.venv/Scripts/python.exe figures.py             # charts in figures/
```

| File | Purpose |
|---|---|
| `twin.py` | Network model, SCADA pump schedule, demand variation, leak model |
| `generate.py` | Simulated sensor dataset (`data/dataset.npz`) |
| `train.py` | Calibration, detection, sensor placement, localisation, metrics |
| `isolate.py` | Valve isolation impact, water lost vs conventional response |
| `figures.py` | Charts for the concept note and video |
| `HARDWARE.md` | Field node design, bill of materials, path from simulation to deployment |

## Simulation set-up

- Network: EPANET Net3 benchmark (97 nodes, 119 pipes, 2 sources, 3 tanks, 2 pumps).
- Each scenario is one day at 15-minute steps, simulated with pressure-dependent demand.
- Reality differs from the twin: every junction's demand varies ±5 %, the whole city ±2 %.
- Sensor noise: pressure 0.05 m per 15-minute reading, total supply 0.2 %, smart meters 1 %.
- Leaks: orifice 8 to 40 mm (log-uniform), random location among 88 junctions, start
  10:00 to 22:00.
- 70/30 train/test split. Thresholds are set on normal training days only, and scored on
  unseen days.

## Limits (stated honestly)

- Results come from simulation. Real networks have model errors larger than ±5 % demand
  noise, so field calibration is the first step of a pilot.
- Net3 is a trunk network with large pipes and tanks, so small leaks barely move pressure.
  In real deployments the network is split into district metered areas (DMAs), which makes
  smaller leaks visible.
- Isolation assumes a motorised valve on each pipe around a node. Real networks isolate
  segments between existing valves.
