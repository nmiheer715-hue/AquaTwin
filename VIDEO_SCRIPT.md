# AquaTwin demo video (4 min 50 s)

Required by the PDF: the problem and who it affects; the solution running in simulation,
showing how it perceives, decides and acts; results; the path to physical hardware. Maximum
5 minutes.

**Screens to have open:** the control room (`aquatwin_out/ltown/dashboard.html`, full
screen), the app (http://127.0.0.1:8050) with a plan already run, `figures/` and
`battledim/figures/`.

**Recording:** 1920×1080, browser at 100 % zoom, OBS or the Windows Game Bar (Win+G).
Voice-over recorded separately reads better.

---

### 1. Problem (0:00–0:35)

**On screen:** a burst-main news photo or a street flooding clip (use your own or one that
is free to use), then a title card: "AquaTwin".

**Voice-over:**
> Indian cities lose a large share of the water they treat before it reaches anyone. Most of
> it leaks from pipes we can't see. A burst is found when a road floods; a slow leak can run
> for weeks. Utilities in London, Valencia and Washington use AI and sensors to catch these
> early, but those systems are proprietary and expensive. AquaTwin brings the same approach
> to Indian towns with low-cost hardware.

### 2. Perceive (0:35–1:05)

**On screen:** the control room in Plan view. Hover over the sensor dots, the district
colours, and the tanks and reservoirs. Briefly show the ESP32 node photo or the parts list
from `HARDWARE.md`.

**Voice-over:**
> This is L-Town, the international leak-detection benchmark: 782 junctions and 33 pressure
> loggers. Our field node is an ESP32 with a pressure transducer and LoRa radio, for about
> ₹4,650. Every 5 minutes, pressures, inlet flows, tank levels and smart-meter readings reach
> the digital twin.

### 3. Decide (1:05–2:10)

**On screen:** press **Play**. Let 2–3 alarms appear, with the feed filling and the zone
charts stepping up. Pause on a big alarm and show the detail panel (size, suspected pipe,
candidate zone). Point at the night-flow chart where the step happens.

**Voice-over:**
> AquaTwin splits the network into metered districts on its own. For each district it keeps a
> water balance, or watches the minimum night flow, when almost nobody uses water. It learns
> what a normal week looks like. When the night flow rises and stays up, that's a new leak,
> and the rise tells us its size: here, 28 cubic metres an hour. To find where, it compares the
> pressure drop at every logger with leak signatures our hydraulic twin computes for every
> junction. Flow says how big, pressure says where.

**On screen (1:30–2:10):** click **3D terrain**. Let the camera tilt; drag to orbit once.

> In 3D, each column rises from the suspected pipe, and its height is the leak size. The rings
> are the candidate zone a crew would search.

### 4. Act (2:10–2:55)

**On screen:** click **Dispatch acoustic crew**, then **Close isolation valves**, and show the
action log. Cut to the plan page and set **Colour: pressure saving** (3D), then
**Colour: chlorine** with the purple sensor markers.

**Voice-over:**
> The system acts. It closes motorised valves around a leak, or sends a crew to the zone. In
> simulation, closing the right valves stopped the leak every time. It also runs smart
> pressure management: the twin turns the pressure-reducing valves down hour by hour, keeping
> every home above 17 metres. On L-Town that cuts leakage by about a fifth, 112,000 cubic
> metres on the 2019 leaks, including the ones we never pinpointed. The same twin tracks water
> quality: where chlorine falls below the safe limit, and where chlorine sensors should go.

### 5. Results (2:55–3:40)

**On screen:** tick **Compare with answer key**. The columns turn green or red and the KPIs
fill in. Play to the end of the year. Then show `battledim/figures/b3_leaderboard.png`.

**Voice-over:**
> We scored AquaTwin with the official algorithm of BattLeDIM, the international competition
> where 18 teams from 13 countries competed on this town. It found 15 of 23 leaks with 6 false
> alarms, worth €303,000 in water saved. That's in line with the winning teams from TU Delft
> and Tongji University, who submitted blind; we're open in our repository about what we
> tuned after seeing the answers. On a second city it had never seen, it caught 4 of 5 bursts
> in the right district.

### 6. Any city, and the path to hardware (3:40–4:35)

**On screen:** the app home page. Upload an `.inp` file, or click **Use the L-Town sample**.
Show the plan page: proposed districts, ranked loggers, and the slider moving from 10 to 30
loggers with the coverage and ₹ cost changing.

**Voice-over:**
> Any utility can start with just its pipe network file. AquaTwin proposes district meters and
> ranks where loggers should go, with the cost. For L-Town it predicted 64 % of leaks
> localisable with its 33 sensors; in the benchmark they achieved 65 %. For the finale we'll
> build a tabletop pipe loop: ESP32 pressure nodes, a flow sensor, solenoid bursts and a
> motorised valve, running this same code live.

**On screen:** the rig sketch or parts on a desk (from `HARDWARE.md`). **Strongly
recommended:** 10 seconds of a real ESP32 node reading pressure on a hose.

### 7. Close (4:35–4:50)

**On screen:** title card: "AquaTwin · Track 4: AI in Water Management", team names, repo link.

**Voice-over:**
> AquaTwin: sensors that listen to the network, AI that finds the leak, and valves that stop
> it. Built for Indian cities. Thank you.
