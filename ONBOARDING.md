# Using AquaTwin on your own network

AquaTwin works on any water network that has an EPANET model. There are two ways to
start, depending on what the utility already has.

## Start the app

```bash
cd ihack_water
.venv/Scripts/python.exe -m aquatwin.app
```

Open http://127.0.0.1:8050. Everything runs on this computer; files are not uploaded
anywhere else.

## 1. Plan sensors: you have the pipe network only

Upload the network as an EPANET `.inp` file with node coordinates. Most tools export one:
EPANET, WaterGEMS/WaterCAD, InfoWater, or QGIS with the QWater plugin.

AquaTwin returns:

- **Proposed metered zones.** It uses the existing pressure-reducing valves, pumps and
  source mains as boundaries. Where a zone is still too large, it proposes extra boundary
  meters, cutting the network at the fewest pipes. Leaks only show above normal demand swings
  when a zone is small, which is why utilities build district metered areas (DMAs).
- **Ranked pressure-logger locations.** Each logger goes where it most improves the
  simulated ability to pinpoint a leak.
- **Coverage for 1 to N loggers.** Detectable is the share of locations where a 2.5 L/s
  leak moves a logger by 3 cm. Localisable is the share pinpointed to within 300 m in a noisy
  simulation. On L-Town the planner rates its 33 real sensors at 64 % localisable; on the
  2019 benchmark leaks they achieved 65 %.

The plan also includes **network health**:

- **Smart pressure management.** An hour-by-hour schedule for every pressure-reducing valve,
  keeping customers at or above 17 m (CPHEEO) plus 2 m, and the leakage saving (FAVAD).
  Networks without PRVs are told so.
- **Water quality.** Water age and chlorine residual (1.0 mg/L at sources, first-order decay),
  the junctions below 0.2 mg/L, and recommended chlorine sensor locations.

The map colour selector switches between zones, pressure saving, water age and chlorine, in
plan view and in 3D.

Monitoring with SCADA data also adds **forecasting** (the control room's Forecast tab, and
`forecast.json`). It gives each metered zone's demand for the next 24 hours, made at
midnight, scored against "same as yesterday" and "same as last week". Each tank that has a
level sensor, a metered pump and level controls in the model gets a day-ahead level
trajectory, with low-level days flagged. Turn it off with `"forecast": false` in the config.

The files are `plan.html` (the map), `recommended_loggers.csv` and `plan.json`. Run the two
health checks on their own with:

```bash
.venv/Scripts/python.exe -m aquatwin.pressure my_city.inp --min 17
.venv/Scripts/python.exe -m aquatwin.quality my_city.inp
```

From the command line:

```bash
.venv/Scripts/python.exe -m aquatwin.plan my_city.inp --sensors 20 --existing J12,J40
```

## 2. Monitor leaks: you have the network and SCADA data

| Data | Required | CSV columns |
|---|---|---|
| Network model `.inp` | yes | |
| Pressures | yes | timestamp, then one column per logger named with its **junction ID** (m) |
| Flows | yes | timestamp, then one column per meter named with its **link ID**; positive in the link's EPANET direction |
| Tank levels | recommended | timestamp, then one column per **tank ID** (m) |
| Smart meters (AMR) | optional | timestamp, then one column per customer **junction ID** |

Each kind can be split over several files (e.g. one per year). The separator and decimal
mark are detected automatically, so `;` with `,` decimals works too. Use any regular
interval: 5 or 15 minutes are typical.

What AquaTwin does with it, automatically:

1. **Zones.** It cuts the network at every flow meter. Each part with customers is a zone,
   and its net inflow is its boundary meters minus the storage change of its tanks. A meter
   that water can bypass is reported and not used.
2. **Indicator per zone.** Where smart meters cover at least 90 % of a zone's demand, it
   uses a water balance (inflow minus metered use). Otherwise it uses the minimum night flow.
3. **Calibration from your data.** It learns the weekly pattern and the day-to-day noise.
   The alarm threshold is 4× that noise (adjustable).
4. **Detection and localisation every morning.** The leak size comes from the flow rise;
   the pressure change pattern, matched against the model, gives the location. Output: zone,
   size, suspected pipe and candidate nodes.

Outputs: `dashboard.html` (control room), `alarms.csv`, `setup.json` (zones, meters,
thresholds, warnings) and, if you give known leaks, `evaluation.json`.

From the command line, with a config file (see `examples/ltown.json`):

```bash
.venv/Scripts/python.exe -m aquatwin.run examples/ltown.json --truth battledim/truth_2019.csv
```

## What to expect

| Network | Data | Pinpointed within 300 m | Detected in the right zone | False alarms |
|---|---|---|---|---|
| L-Town (BattLeDIM), generic engine, no tuning | real-format SCADA, 33 loggers, 82 smart meters | 15 of 23 | 23 of 23 (one zone covers 88 % of the network, so this is generous) | 11 |
| Net3, a network AquaTwin was never tuned for | 90 days simulated, 10 planned loggers, 5 planned districts | 0 of 5 | 4 of 5 (median 7 days) | 4 |

- **Zone detection is the reliable part.** "District Z1 has been losing about 100 m³/h
  since last night" is what starts a step test or an acoustic survey.
- **Pinpointing depends on logger density and pipe sizes.** Large trunk mains barely
  change pressure when they leak. Run the planner first; its localisable figure tells you
  what to expect.
- **Intermittent supply.** With 2 to 6 hours of supply a day, pipes drain and refill and
  night flow does not exist. The water balance per zone still works when inflow and
  consumption are metered; pressure pinpointing will be weak.

## Common problems

| Message | Fix |
|---|---|
| "no metered zone found" | Flow CSV column names must be EPANET **link** IDs at zone inlets |
| "flow meter on X is not on a zone boundary" | A parallel pipe bypasses that meter. Meter the main itself |
| "Zn has 0 pressure sensor(s)" | That zone still gets leak alarms, but no pipe location. Add loggers (run the planner) |
| Columns "not found in the model" | IDs in the CSV header must match the `.inp` exactly, including case |
