"""Water saved on the real 2019 L-Town leaks if AquaTwin's pressure schedule
had been running (FAVAD, N1 = 0.5 / 1.0 / 1.5). Uses the leak flow series from
the answer key and the hourly pressure ratio at each leak's pipe."""
import json
import os

import numpy as np

import network
import scoring

HERE = os.path.dirname(os.path.abspath(__file__))
PM = os.path.join(HERE, "..", "aquatwin_out", "ltown", "pressure_management.json")


def main():
    pm = json.load(open(PM))
    ratio = {n: np.array(v) for n, v in pm["node_ratio"].items()}
    wn = network.model()
    G = network.Distances(wn)
    out, tot = [], {0.5: 0.0, 1.0: 0.0, 1.5: 0.0}
    leak_total = 0.0
    hours = (np.arange(105120) % 288) // 12
    for lk in scoring.leak_table(2019):
        l = wn.get_link(lk["link"])
        cands = [n for n in (l.start_node_name, l.end_node_name) if n in ratio]
        if not cands:                                   # leak outside a PRV area (district C, pumped)
            near = None
        else:
            near = cands[0]
        q = lk["series"]                                # m3/h, 5-min steps
        vol = q.sum() / 12
        leak_total += vol
        row = dict(link=lk["link"], volume_m3=round(float(vol), 1), in_prv_area=near is not None)
        for n1 in tot:
            if near is None:
                saved = 0.0
            else:
                r = ratio[near][hours[:len(q)]]
                saved = float((q * (1 - np.clip(r, 0, None) ** n1)).sum() / 12)
            row[f"saved_m3_N1_{n1}"] = round(saved, 1)
            tot[n1] += saved
        out.append(row)
    res = dict(leak_volume_2019_m3=round(leak_total, 1),
               saved_m3={str(k): round(v, 1) for k, v in tot.items()},
               saved_share={str(k): round(v / leak_total, 3) for k, v in tot.items()},
               saved_eur_at_0_80={str(k): round(v * 0.8) for k, v in tot.items()},
               saved_inr_at_20={str(k): round(v * 20) for k, v in tot.items()},
               leaks=out)
    json.dump(res, open(os.path.join(HERE, "results", "pressure_value_2019.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "leaks"}, indent=1))


if __name__ == "__main__":
    main()
