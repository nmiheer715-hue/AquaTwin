# AquaTwin: Physical AI that finds water leaks and shuts them off

**Track 4: AI in Water Management (leak detection)** · TIH IIT Bombay Physical AI Hackathon, i-Hack 2026  
**Team Green Byte:** Miheer Nikam · Nihaal R  
**Repository:** [github.com/nmiheer715-hue/AquaTwin](https://github.com/nmiheer715-hue/AquaTwin) · **Demo video:** [youtu.be/4Di41-71QSA](https://youtu.be/4Di41-71QSA) (4:26)

---

## 1. Problem

Indian cities lose a large share of the water they treat and pump before it reaches anyone,
mostly through leaks in buried pipes. A burst main is found when a road floods or someone
complains; a slow leak can run for weeks. AMRUT 2.0 asks cities to bring non-revenue water
below 20 %, but most utilities still find leaks by waiting for complaints or sending crews
to walk the network with listening sticks.

**Who it affects:** utilities (lost revenue and pumping energy), households at the tail end
of the network (low pressure, irregular supply), and everyone downstream of a burst (road
damage, contamination risk through depressurised pipes).

Utilities abroad have moved on. Thames Water runs AI across 75,000 acoustic sensors, Valencia
runs a digital twin of its network, and DC Water triangulates leaks from 120 pressure
sensors. These systems are proprietary and priced for large Western utilities.

## 2. Approach: perceive, decide, act

AquaTwin is a closed loop between sensors in the pipes, a digital twin of the network, and
valves that act on its decisions.

**Perceive.** Low-cost pressure nodes (ESP32 + 0–10 bar transducer + LoRa) on the mains,
flow meters at district inlets, tank-level sensors and, where they exist, customer smart
meters. Readings arrive every 5 to 15 minutes.

**Decide.** Four AI and estimation stages run every morning after the 02:00 to 04:00 night window:

1. **Self-configuring water balance.** The network is cut at every flow meter into metered
   districts. Each district gets an exact water balance (inflow minus tank storage minus
   smart-meter use) or its minimum night flow, the indicator UK utilities use.
2. **Learned normal behaviour.** The weekly demand pattern and day-to-day noise are learned
   from the data, so alarms adapt to each city with no hand tuning. The threshold is 4× the
   measured noise.
3. **Change detection.** A sustained rise in a district's indicator is a new leak, its size
   in m³/h. A drop is a repair.
4. **Physics-informed localisation.** The night pressure change at every sensor is matched
   against leak signatures computed by the hydraulic twin (EPANET) for every pipe junction.
   The flow rise fixes the leak size; the pressure pattern fixes the place. A matching-pursuit
   step separates several simultaneous leaks.

**Act.** Each alarm names the district, the size, the suspected pipe and a candidate zone. The
system can then close motorised isolation valves around it, or send an acoustic crew to search
the zone. In simulation, closing the valves on the correct node stopped the leak flow in 100 %
of tests.

A **planning mode** needs only the city's pipe network file. It proposes district boundaries
and ranks where pressure loggers should go, so a utility can size the hardware before buying
any.

**Smart distribution and water quality** use the same twin and hardware:

- **Pressure management.** For each hour, the twin finds how far each pressure-reducing valve
  can be turned down while every customer keeps at least 17 m (the CPHEEO 3-storey minimum)
  plus a 2 m margin. Lower pressure shrinks every leak, including those never pinpointed. The
  valve nodes apply the schedule.
- **Water quality.** EPANET's quality engine simulates water age and chlorine decay. It flags
  areas below the 0.2 mg/L tap minimum (BIS 10500) and recommends chlorine sensor locations.
  Low residual next to a leak or a low-pressure area marks a contamination risk.
- **Demand and reservoir forecasting.** Every midnight a gradient-boosted model forecasts each
  district's demand for the next 24 hours. The twin then rolls each service tank forward hour
  by hour, using the pump's own level controls, so operators can see a low-level day coming
  and schedule pumping in cheaper off-peak hours.

## 3. System architecture

```
 FIELD (every 5-15 min)                    TWIN + AI (local server / cloud)                 FIELD (on alarm)
 Pressure nodes  ESP32+transducer ─LoRa─┐   Hydraulic twin (EPANET via WNTR)                 Valve nodes
 Inlet flow meters, tank levels ─SCADA──┼─▶ Zone discovery → water balance / night flow  ─▶  ESP32 + relay +
 Customer smart meters (AMR) ───────────┘   Learned weekly pattern + noise → detection         motorised valve
                                            Leak signatures → localisation → candidate zone ─▶ Acoustic crew
                                            Control room UI: map, alarms, replay, 3D view       (zone search)
```

| Layer | Prototype choice | Why |
|---|---|---|
| Pressure node | ESP32, 0–10 bar 0.5–4.5 V transducer, ADS1115 16-bit ADC, LoRa SX1276, Li-SOCl₂ cell; about ₹4,650 | 1 Hz sampling averaged to 15 min gives the 2–5 cm noise the AI assumes; over 2 years on battery |
| Telemetry | LoRa (433/865 MHz) to a gateway | Our team has built and tested a two-board ESP32 + RA-02 LoRa link with packet resend |
| Valve node | ESP32 + relay + 12/24 V motorised ball valve with limit-switch feedback; or a PRV pilot actuator for pressure schedules | The twin knows the valve's real state |
| Quality node | ESP32 + free-chlorine (ORP proxy) and turbidity probes, about ₹2,500 extra | Placed where the twin predicts the lowest residual |
| Twin and AI | Python: WNTR/EPANET, NumPy, scikit-learn; Flask app | Open standard: any utility model exports to EPANET `.inp` |
| Simulation environment | EPANET (US EPA), the industry-standard water-network simulator | Plays the role Gazebo plays for robots: physically accurate pressures and flows, including leaks and valve closures |

**Technology readiness (TRL 4).** Validated against the international BattLeDIM benchmark,
which supplies two years of real-format SCADA data for a real town's layout. The full
sensor-to-valve loop is validated in simulation, and the telemetry hardware is built and
tested.

## 4. Results and expected impact

**International benchmark: BattLeDIM 2020 (L-Town, Cyprus).** This is the standard test
run by KIOS (University of Cyprus) with TU Delft, Technion and Tsinghua. L-Town has 782
junctions, 33 pressure sensors, 82 smart meters and 33 hidden leaks. We scored our results
with a port of the official algorithm that reproduces the official perfect score exactly.

| | Leaks found | False alarms | Economic score (2019) |
|---|---|---|---|
| **AquaTwin (4σ setting)** | **15 of 23 (65 %)** | **6** | **€303,324** |
| 2020 joint winners (Tongji; TU Delft "Under Pressure") | 56–65 % | 3–4 | €260,562 – €264,873 |

The 2020 teams submitted blind; the 2019 answer key is now public. We developed on 2018 and
disclose the design choices made after seeing 2019 results in the repository. The fair claim
is that AquaTwin is competitive with the best published methods.

- **Generalisation.** The self-configuring engine reaches 15 of 23 on L-Town with no tuning.
  On a city it had never seen (EPANET Net3, 90 days of simulated SCADA, 5 hidden bursts), it
  flagged 4 of 5 in the right district.
- **Speed and savings.** In a 2,000-leak simulation, every leak of 20 L/s or more was
  detected, with a median of 30 minutes from start to alarm. Water lost was 77 % lower than
  waiting for a report.
- **The planner predicts field performance.** It rated L-Town's 33 real sensors at 64 %
  localisable; they achieved 65 % on the benchmark.
- **Pressure management (L-Town).** Average pressure falls from 48 to 38 m in district A and
  from 37 to 23 m in district B, with every customer at or above 19 m. Leakage falls 21 % and
  38 % (FAVAD, N1 = 1.0). Applied to the real 2019 leaks, that saves **111,947 m³, 17 % of all
  leaked water (about ₹22 lakh at ₹20/m³)**, on top of detection. The range is 9–24 % for
  N1 = 0.5–1.5.
- **Water quality (L-Town, simulated).** Median water age is 2.5 h, but the oldest 5 % of the
  network holds water over 34 h. 5 junctions fall below 0.2 mg/L free chlorine, and 5 chlorine
  sensor locations are recommended. The benchmark has no measured quality data, so this part
  is validated in simulation only.
- **Forecasting (L-Town, real 2019 data, trained on 2018 only).** The day-ahead demand error is
  3.2 % in district A, against 4.6 % for the best simple rule ("same as last week"). In
  district B it is 9.5 % against 9.8 %. Tank T1's level is forecast a day ahead to within
  0.19 m on average (90 % within 0.44 m) over a 1.95–3.9 m operating range.

**Expected impact for an Indian district metered area of 2,000 to 5,000 connections:**

- about ₹50,000 of sensors;
- bursts flagged by the next morning instead of after days;
- crews sent to a candidate zone of a few hundred metres instead of a whole ward.

The method suits the 24×7 supply zones being built under AMRUT 2.0. In intermittent-supply
areas, the per-zone water balance still flags which district is losing water.

**Path to reality.**

1. **Stage 3 prototype.** A tabletop pipe loop with ESP32 pressure nodes, a flow sensor,
   solenoid "bursts" and motorised valves, running the same code live against an EPANET model
   of the loop. Open a burst, and the system alarms, names the branch and closes the valve.
2. **Pilot.** One DMA modelled from GIS. 8–12 nodes at the planner's locations. Four weeks in
   shadow mode to calibrate, then live alarms, valve control and the pressure schedule.
3. **Next.** Measured chlorine and turbidity to calibrate the quality model. Wastewater
   networks (sewer flow and treatment-plant monitoring, with a SWMM model) and flood
   forecasting from rainfall and reservoir inflow follow the same twin-plus-sensors approach.
