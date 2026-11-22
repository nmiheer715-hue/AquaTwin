# How the BattLeDIM result was obtained

**Scoring.** `scoring.py` ports the official KIOS algorithm (`Scoring_Algorithm.m`,
`scoring_function.m`). It counts a hit when the reported pipe is within 300 m and the time
falls while the leak runs. It values the water saved at €0.80/m³, deducts a crew cost of up to
€500 by distance, and charges €500 per false alarm. It reproduces the official perfect score,
€523,153.82.

**Development data.** We built on 2018, the historical year, using its leak answers and repair
log, which were part of the competition's historical dataset.

**Selection rules.**
- Alarm thresholds are multiples of the measured daily noise of each district's indicator in
  2018.
- Localisation settings were chosen by a sweep on 2018 only (`sweep.py` B).
- The year-end check that reports leaks still running on 1 January was validated at 2018 month
  ends (`sweep.py` A).

**Choices made after seeing 2019 results** (the 2020 teams submitted blind):
1. aligning the weekly demand pattern to the start of each year;
2. bounding the localisation fit by the leak size from the flow signal;
3. replacing score-tuned thresholds with noise-based ones (score-tuning on 2018 overfitted:
   €214k on 2019);
4. the 4σ operating point, picked for fewer false alarms. The setting selected on 2018 alone is
   2.5σ: 18 of 23 found, 13 false alarms, €343,806.

**Tested and not adopted.** We calibrated the twin's roughness and demand factors on the
leak-free first week. Net inflow error fell from 21.3 to 3.6 m³/h, but localisation on 2018 did
not improve (2 more false alarms), so we kept the published model.
