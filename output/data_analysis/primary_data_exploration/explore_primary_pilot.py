"""Exploratory analysis of the 6-fruit/96-scan jambu kristal PRIMARY pilot dataset.

Purpose of the pilot (per team): (1) functional check -- can the sensor/pipeline
acquire and store data reliably; (2) visibility check -- is there an apparent
spectral difference between "busuk" (anomali) and "tidak" (normal) labels.
NOT intended for training a predictive model (n=1 fruit per anomali class --
any classifier evaluation here would be unreliable/overfit to one specimen).
"""
import os
import pandas as pd
import numpy as np
from scipy import stats

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "..", "..", "uji_labeled_buahsafe_dataset_fixed.csv")
OUT_DIR = BASE

CHANNELS = ["nm410", "nm435", "nm460", "nm485", "nm510", "nm535", "nm560", "nm585",
            "nm610", "nm645", "nm680", "nm705", "nm730", "nm760", "nm810", "nm860", "nm900", "nm940"]


def main():
    df = pd.read_csv(SRC)

    # (a) functional validation
    n_rows = len(df)
    n_missing = df[CHANNELS].isna().sum().sum()
    n_nonfinite = (~np.isfinite(df[CHANNELS].values)).sum()
    struct = df.groupby("fruit_id").agg(
        n=("scan_no", "size"), label=("label", "first"),
        diameter_min=("diameter_cm", "min"), diameter_max=("diameter_cm", "max"),
        jarak_cm=("jarak_cm", lambda x: sorted(x.unique())),
    )
    print("=== (a) Validasi fungsional ===")
    print(f"Total baris: {n_rows}, nilai kosong: {n_missing}, nilai non-finite: {n_nonfinite}")
    print(struct.to_string())
    struct.to_csv(os.path.join(OUT_DIR, "struktur_6_buah.csv"))

    # (b) visibility test: Welch t-test + Cohen's d per channel
    norm = df[df.label == "normal"]
    anom = df[df.label == "anomali"]
    print(f"\n=== (b) Uji keterlihatan beda (normal n={len(norm)}, anomali n={len(anom)}) ===")

    rows = []
    for c in CHANNELS:
        t, p = stats.ttest_ind(norm[c], anom[c], equal_var=False)
        n1, n2 = len(norm), len(anom)
        sp = np.sqrt(((n1 - 1) * norm[c].var(ddof=1) + (n2 - 1) * anom[c].var(ddof=1)) / (n1 + n2 - 2))
        d = (norm[c].mean() - anom[c].mean()) / sp
        rows.append({
            "channel": c,
            "mean_normal": round(norm[c].mean(), 2),
            "mean_anomali": round(anom[c].mean(), 2),
            "p_value": p,
            "signifikan": "Ya" if p < 0.05 else "Tidak",
            "cohens_d": round(d, 2),
        })
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUT_DIR, "uji_beda_18_kanal.csv"), index=False)
    pd.set_option("display.width", 120)
    print(res.to_string(index=False))
    print(f"\nJumlah kanal signifikan (p<0.05): {(res['signifikan']=='Ya').sum()} / {len(CHANNELS)}")

    nir = res[res["channel"].isin(["nm730", "nm760", "nm810", "nm860", "nm900", "nm940"])]
    print(f"Rata-rata |Cohen's d| kanal NIR (730-940nm): {nir['cohens_d'].abs().mean():.2f}")
    uvvis = res[~res["channel"].isin(["nm730", "nm760", "nm810", "nm860", "nm900", "nm940"])]
    print(f"Rata-rata |Cohen's d| kanal UV-VIS (410-705nm): {uvvis['cohens_d'].abs().mean():.2f}")


def _selfcheck():
    df = pd.read_csv(SRC)
    assert len(df) == 96
    assert df["fruit_id"].nunique() == 6
    assert set(df.groupby("fruit_id").size().unique()) == {16}


if __name__ == "__main__":
    _selfcheck()
    main()
