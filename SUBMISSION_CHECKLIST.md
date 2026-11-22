# i-Hack 2026 · TIH Physical AI Hackathon: submission checklist

Source: the TiH problem statement PDF (Track 4: AI in Water Management). Stage 1 deadline:
**24 Nov 2026**.

## What must be submitted

| # | Item | Requirement (PDF) | Status | File / action |
|---|---|---|---|---|
| 1 | Demo video | max **5 min**: problem and who it affects; solution running in simulation (perceive, decide, act); results; path to physical hardware | Done: `video/film/AquaTwin_iHack2026_demo_voiced_1.1x.mp4` (4:26, 1080p, cloned-voice narration, 1.1× speed) | Upload and add the link. Real-voice backup: `video/film/AquaTwin_iHack2026_demo_realvoice.mp4` |
| 2 | Concept note | **2–3 pages**: problem, approach, system architecture, expected impact | Drafted | `CONCEPT_NOTE.md`. Fill in team names and links, then export to PDF |
| 3 | Code repository | GitHub link | To push | Push the `ihack_water/` folder (see "Before pushing") |
| 4 | Team details and track | Track 4: AI in Water Management | Need names | Add to the concept note header and the registration form |
| 5 | Registration | https://www.ecell.in/esummit/ihack/reg | You | Team of 2 to 5 (website says 1 to 4: stay at 2 to 4) |

## Eligibility and disqualification rules

| Rule | How AquaTwin meets it |
|---|---|
| AI combined with a physical system (sensors, actuators, connected devices) | ESP32 pressure nodes, LoRa telemetry, motorised valve nodes; the "act" step closes valves. Show hardware in the video (see VIDEO_SCRIPT, segment 5) |
| Out of scope: theoretical models without physical integration | Lead with the sensor-to-valve loop, not only the algorithm |
| TRL above 3 | Validated on real-format SCADA (BattLeDIM), the full loop in simulation, telemetry hardware built (TRL 4). **Strongly recommended:** film one real ESP32 pressure node streaming into AquaTwin |
| Original work; open source allowed with attribution | Credit WNTR/EPANET, scikit-learn, three.js and the BattLeDIM dataset (KIOS, CC licence) in the README |
| Missing video or concept note = not evaluated | Both are required. Submit early |

## How judges score, and where we answer each part

| Criterion | Weight | Our strongest evidence | Where |
|---|---|---|---|
| Problem relevance and impact | 20 % | Non-revenue water in Indian cities, AMRUT 2.0 target, affected groups | Note §1, video 0:00–0:35 |
| Technical depth of the AI | 25 % | Self-configuring water balance, learned noise model, change detection, physics-informed localisation with matching pursuit | Note §2, video 0:35–2:10 |
| Simulation quality and results | 20 % | BattLeDIM benchmark (15/23, 6 false alarms, €303k, official scoring), unseen network, 2,000-leak study | Note §4, video 2:10–3:40 |
| Sim-to-real feasibility | 20 % | Parts list with costs, built LoRa link, valve node, tabletop rig, pilot plan, planner predicting field accuracy | Note §3–4, video 3:40–4:35 |
| Innovation | 10 % | Works on any network from its `.inp` file; planner sizes sensors before purchase; one twin covers leak detection, smart pressure management, water quality and day-ahead demand and tank forecasting; 3D control room | Video 1:30–2:55, 4:35 |
| Presentation | 5 % | Control room, clear script, honest caveats | Whole video |

## Before pushing to GitHub

- Do **not** commit `battledim/raw/` (about 200 MB of dataset files) or `.venv/`.
  Link Zenodo record 4017659 and `load.py` instead.
- Leave `aquatwin_jobs/`, `aquatwin_out/`, `data/*.npz` and `results/model.pkl` out too.
- Add a licence (MIT) and a credits section to the README.

## Open items for the team

1. Team name and members, for the note header.
2. Record the video (about 2 hours with the script).
3. Optional, but strongly helps TRL: one ESP32 + pressure transducer on a hose or tap,
   streaming into the app.
4. Export `CONCEPT_NOTE.md` to PDF and check it fits 3 pages.
