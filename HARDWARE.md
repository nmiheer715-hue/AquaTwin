# From simulation to reality: field hardware

## System architecture

```
 FIELD (every 15 min)                         CONTROL ROOM / CLOUD                  FIELD (on alarm)
 ┌────────────────────────┐   LoRaWAN /     ┌──────────────────────────────┐      ┌─────────────────────┐
 │ Pressure node (x10)    │   NB-IoT        │ Digital twin (EPANET/WNTR)   │      │ Valve node          │
 │  ESP32 + 0-10 bar      │ ──────────────▶ │ Calibration  → residuals     │ ───▶ │  ESP32 + relay      │
 │  transducer, battery   │                 │ Detector     → alarm         │      │  motorised valve    │
 ├────────────────────────┤                 │ Localiser    → top-5 zone    │      │  position feedback  │
 │ Supply + tank meters   │ ── SCADA ─────▶ │ Valve planner→ least impact  │      └─────────────────────┘
 │ Large-customer meters  │ ── AMR  ──────▶ │ Dashboard + crew dispatch    │ ───▶  Acoustic crew (zone)
 └────────────────────────┘                 └──────────────────────────────┘
```

## Pressure node (the part we build)

| Part | Example | Approx. cost (INR) |
|---|---|---|
| MCU + radio | ESP32 + SX1276 LoRa module (433/865 MHz) | 900 |
| Pressure transducer | 0-10 bar, 0.5-4.5 V, stainless, 1/4" BSP | 1,500 |
| ADC | ADS1115, 16-bit | 250 |
| Power | 3.6 V Li-SOCl2 D-cell or 18650 + small solar panel | 800 |
| Enclosure + fittings | IP68 box, tapping saddle / hydrant adaptor | 1,200 |
| **Total per node** | | **~4,650** |

Firmware: average 15 min of readings at 1 Hz (this is what brings noise down to the 0.05 m
the simulation assumes), timestamp them, send one packet per 15 min, deep-sleep in
between. Expected battery life is over 2 years at that duty cycle.

Our team has already built and tested a two-board LoRa telemetry link with packet resend
(ESP32 + RA-02, SF8/BW250), plus a simulator of that link. The pressure node reuses it.

## Valve node

ESP32 + relay board driving a 12/24 V motorised ball valve (DN50 prototype), with
limit-switch feedback so the twin knows the valve's actual state. Commands are signed and
need operator confirmation, unless the alarm confidence and leak size pass an
auto-isolate rule.

## Finale prototype (Stage 3)

A tabletop pipe loop to show the full sense → decide → act cycle on real hardware:

- 3 m of 20 mm PVC pipe in a loop with 4 tee junctions, fed by a small pump and header tank
- 3 pressure nodes + 1 flow sensor (YF-S201) on the supply line
- 2 leak points (solenoid valves that open to simulate a burst)
- 2 motorised isolation valves
- Laptop running the same detection + localisation code against an EPANET model of the loop

Live demo: open a leak solenoid → the dashboard alarms within a minute → it names the
leaking branch → the isolation valve closes → flow returns to normal.

Estimated rig cost: INR 12,000 to 15,000.

## Pilot path (after the hackathon)

1. Pick one DMA (2,000 to 5,000 connections) and get its GIS + pipe data into EPANET.
2. Install 8 to 12 pressure nodes at the sites the placement optimiser picks, plus a
   level sensor on each service reservoir.
3. Run 4 weeks in shadow mode to calibrate the twin and tune the alarm threshold.
4. Go live with alarms + crew dispatch. Add motorised valves on 2 or 3 critical mains.
