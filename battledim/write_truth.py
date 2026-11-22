"""Write the 2019 leak answer key as link_id,start,end (for aquatwin --truth)."""
import os

import scoring

HERE = os.path.dirname(os.path.abspath(__file__))
rows = ["link_id,start,end"] + [f"{l['link']},{l['start']:%Y-%m-%d %H:%M},{l['end']:%Y-%m-%d %H:%M}"
                                for l in scoring.leak_table(2019)]
open(os.path.join(HERE, "truth_2019.csv"), "w").write("\n".join(rows) + "\n")
print(len(rows) - 1, "leaks written")
