"""Load the BattLeDIM SCADA CSVs into one fast .npz cache.

Arrays (5-minute steps): pressures (m), flows (m3/h), tank level (m),
AMR demands (L/h), and the leak answer keys (m3/h), for 2018 and 2019.
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CACHE = os.path.join(HERE, "scada.npz")


def _csv(name):
    df = pd.read_csv(os.path.join(RAW, name), sep=";", decimal=",", index_col=0, parse_dates=True)
    return df


def build():
    out = {}
    for y in (2018, 2019):
        for kind in ("Pressures", "Flows", "Levels", "Demands"):
            df = _csv(f"{y}_SCADA_{kind}.csv")
            out[f"{kind.lower()}_{y}"] = df.values.astype(np.float32)
            out[f"{kind.lower()}_cols"] = np.array(df.columns, dtype=str)
            out[f"time_{y}"] = df.index.values.astype("datetime64[m]")
        lk = _csv(f"{y}_Leakages.csv")
        out[f"leaks_{y}"] = lk.values.astype(np.float32)
        out[f"leaks_cols_{y}"] = np.array(lk.columns, dtype=str)
    np.savez_compressed(CACHE, **out)
    return out


def load():
    if not os.path.exists(CACHE):
        build()
    return dict(np.load(CACHE, allow_pickle=False))


if __name__ == "__main__":
    d = build()
    for k, v in d.items():
        print(k, v.shape, v.dtype)
