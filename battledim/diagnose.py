"""Development aid: list every event with the nearest active true leak."""
import sys

import detect
import network
import scoring

months = [int(m) for m in sys.argv[1:]] if len(sys.argv) > 1 else None
reps, evs = detect.run()
dist = network.Distances()
leaks = {l["link"]: l for l in scoring.leak_table(2018) + scoring.leak_table(2019)}
for e in evs:
    if months and not (e["time"].year == 2018 or e["time"].month in months):
        continue
    act = [k for k, l in leaks.items() if l["start"] <= e["time"] <= l["end"]]
    na = min(act, key=lambda k: dist.pipe(e["pipe"], k)) if act else None
    dm = dist.pipe(e["pipe"], na) if na else float("nan")
    tops = [min(act, key=lambda k: dist.pipe_node(k, n)) for n in e["top"][:1]] if act else []
    print(f"{e['time']:%Y-%m-%d} {e['zone']:>2} +{e['size_m3h']:5.1f} {e['pipe']:>5} growth={str(e['growth']):5} "
          f"nearest active {na} {dm:6.0f} m  top5 {e['top']}")
print("2019 reports:", reps[:6])
