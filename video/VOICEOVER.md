# AquaTwin demo: voice-over sheet

Read each line when its caption appears (times are from the start of the video). The
captions in the film are this exact text, so a line can run a second long or short without
looking wrong. Total 4:53.

**How to record:** phone voice memo or laptop mic in a quiet room, about 20 cm from the mouth.
Record it all in one take, or one file per section. Send me the file(s) (WAV, M4A or MP3)
and I will place them on the timeline, level the volume and render the final MP4.

| Time | Line |
|---|---|
| **1 · Problem** | |
| 0:00 | Indian cities lose a large share of the water they treat before it reaches anyone. |
| 0:06 | Most of it leaks from pipes we can't see. A slow leak can run for weeks. |
| 0:12 | Utilities in London, Valencia and Washington use AI and sensors to catch these early… |
| 0:19 | …but those systems are proprietary and expensive. |
| 0:25 | AquaTwin brings the same approach to Indian towns, with low-cost hardware. |
| **2 · Perceive** | |
| 0:35 | This is L-Town, the international leak-detection benchmark: 782 junctions and 33 pressure loggers. |
| 0:43 | AquaTwin splits the network into metered districts on its own. |
| 0:50 | Our field node is an ESP32 with a pressure transducer and LoRa radio, for about four thousand six hundred and fifty rupees. |
| 0:57 | Every 5 minutes, pressures, inlet flows, tank levels and smart-meter readings reach the digital twin. |
| **3 · Decide** | |
| 1:05 | For each district, AquaTwin keeps a water balance, or watches the minimum night flow. |
| 1:11 | It learns what a normal week looks like, so every city gets its own thresholds. |
| 1:18 | When night flow rises and stays up, that's a new leak. The rise tells us its size. |
| 1:26 | Here, 12.8 cubic metres an hour. To find where, it matches the pressure drop at every logger to leak signatures from the hydraulic twin. |
| 1:36 | In 3D, each column rises from the suspected pipe. Its height is the leak size. |
| 1:50 | The rings mark the candidate zone a crew would search. |
| 2:05 | Flow says how big. Pressure says where. |
| **4 · Act** | |
| 2:10 | The system acts. It closes motorised valves around a leak, or sends a crew to the zone. |
| 2:20 | It also runs smart pressure management, turning the valves down hour by hour while every home stays above 17 metres. |
| 2:27 | And the same twin tracks water quality: where chlorine falls below the safe limit, and where sensors should go. |
| 2:37 | In simulation, closing the right valves stopped the leak every time, and pressure management saves a sixth of all leaked water. |
| **4b · Forecast** | |
| 2:49 | Every midnight it also forecasts tomorrow: each district's demand, and the tank level, so pumping is planned before a tank runs low. |
| **5 · Results** | |
| 3:01 | We scored AquaTwin with the official algorithm of BattLeDIM, where 18 teams from 13 countries competed on this town. |
| 3:12 | It found 15 of 23 leaks with 6 false alarms, worth 303,000 euros in water saved. |
| 3:22 | That's in line with the winning teams from TU Delft and Tongji University, who submitted blind. We're open about what we tuned after seeing the answers. |
| 3:38 | On a second city it had never seen, it caught 4 of 5 bursts in the right district. |
| **6 · Any city and hardware** | |
| 3:46 | Any utility can start with just its pipe network file, and AquaTwin draws it from its own map. |
| 3:55 | It proposes district meters and ranks where loggers should go, with the cost. |
| 4:07 | For L-Town it predicted 64 percent of leaks localisable with its 33 sensors. In the benchmark they achieved 65. |
| 4:20 | For the finale we'll build a tabletop pipe loop: ESP32 pressure nodes, a flow sensor, solenoid bursts and a motorised valve… |
| 4:31 | …running this same code live. Then a pilot in one district, for about fifty thousand rupees of sensors. |
| **7 · Close** | |
| 4:41 | AquaTwin: sensors that listen to the network, AI that finds the leak, and valves that stop it. Built for Indian cities. Thank you. |

**Before submitting:** the closing card shows Team Green Byte (Miheer Nikam, Nihaal R). Add the
GitHub link (`repo` field in `video/film/compositions/close.html`) once the repo is public.
