"""Produce the BattLeDIM submission file and score it.

Writes:
  submission/AquaTwin.txt         official format: "linkID, YYYY-MM-DD HH:MM"
  results/battledim_score.json    Python port of the official scorer (2018 + 2019)
  results/events.json             every event the system raised, with candidates
"""
import json
import os

import detect
import scoring

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    reps, evs = detect.run()
    os.makedirs(os.path.join(HERE, "submission"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "submission", "AquaTwin.txt"), "w") as f:
        f.write("# linkID, startTime\n")
        for link, t in sorted(reps, key=lambda x: x[1]):
            f.write(f"{link}, {t:%Y-%m-%d %H:%M}\n")
    r19 = scoring.score(reps, 2019)
    r18 = scoring.score([(e["pipe"], e["time"]) for e in evs if e["time"].year == 2018 and not e["growth"]], 2018)
    # search-zone reach (not the official score): reported alarms in 2019,
    # plus the carry-over reports on 1 January
    carry = [dict(time=t, pipe=p, top=[]) for p, t in reps if t.year == 2019 and t.month == 1 and t.day == 1 and t.hour == 0]
    rep_set = {(p, t) for p, t in reps}
    alarms19 = carry + [e for e in evs if e["time"].year == 2019 and (e["pipe"], e["time"]) in rep_set]
    zone = scoring.zone_found(alarms19, 2019, dist=detect.prepared()["L"].dist)
    leaderboard = [("Tongji", 264873, 0.56, 3), ("Under Pressure", 260562, 0.65, 4), ("IRI", 210772, 0.43, 1),
                   ("Leakbusters", 195490, 0.47, 7), ("Tsinghua", 167981, 0.47, 5), ("UNIFE", 127626, 0.43, 4)]
    out = dict(
        evaluation_2019=dict(score_eur=r19["total"], tp=r19["tp"], fp=r19["fp"], fn=r19["fn"],
                             n_leaks=r19["n_leaks"], tpr=round(r19["tpr"], 3), detected=r19["detected"],
                             perfect_score_eur=523153.82,
                             zone_found=len(zone), zone_found_leaks=zone),
        development_2018=dict(score_eur=r18["total"], tp=r18["tp"], fp=r18["fp"], n_leaks=r18["n_leaks"],
                              perfect_score_eur=178872.66),
        official_leaderboard_2020=[dict(team=t, score_eur=s, tpr=p, fp=f) for t, s, p, f in leaderboard],
        rows_2019=[dict(r, time=f"{r['time']:%Y-%m-%d %H:%M}") for r in r19["rows"]],
    )
    json.dump(out, open(os.path.join(HERE, "results", "battledim_score.json"), "w"), indent=2)
    json.dump([dict(e, time=f"{e['time']:%Y-%m-%d %H:%M}", top=[str(x) for x in e["top"]]) for e in evs],
              open(os.path.join(HERE, "results", "events.json"), "w"), indent=1)
    print(f"2019: EUR {r19['total']:,.2f}  TP {r19['tp']}/{r19['n_leaks']}  FP {r19['fp']}  "
          f"| inside an alarm's search zone: {len(zone)}/{r19['n_leaks']}")
    print(f"2018: EUR {r18['total']:,.2f}  TP {r18['tp']}/{r18['n_leaks']}  FP {r18['fp']}")


if __name__ == "__main__":
    main()
