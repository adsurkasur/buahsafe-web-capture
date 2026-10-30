"""Normalize label vocabulary in the gabungan dataset (sehat -> normal) and validate consistency."""
import os
import pandas as pd

SRC = os.path.join(os.path.dirname(__file__), "buahsafe_dataset_gabungan_08092026.xlsx")
OUT_XLSX = os.path.join(os.path.dirname(__file__), "buahsafe_dataset_gabungan_08092026_clean.xlsx")
OUT_CSV = os.path.join(os.path.dirname(__file__), "buahsafe_dataset_gabungan_08092026_clean.csv")

LABEL_MAP = {"sehat": "normal"}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["label"] = df["label"].replace(LABEL_MAP)
    return df


def main():
    df_raw = pd.read_excel(SRC)
    df_clean = clean(df_raw)

    # fruit_id prefix must map to exactly one label after cleaning
    prefix = df_clean["fruit_id"].str.extract(r"^([A-Za-z]+)")[0]
    bad = df_clean.groupby(prefix)["label"].nunique()
    inconsistent = bad[bad > 1]
    if len(inconsistent):
        raise ValueError(f"Inconsistent label per fruit_id prefix: {inconsistent.to_dict()}")

    if df_clean.duplicated(subset=["fruit_id", "scan_no"]).any():
        raise ValueError("Duplicate fruit_id/scan_no rows found")

    if df_clean["label"].isna().any() or (df_clean["label"] == "").any():
        raise ValueError("Empty label found")

    df_clean.to_excel(OUT_XLSX, index=False)
    df_clean.to_csv(OUT_CSV, index=False)

    print(f"[OK] {len(df_raw)} rows in, {len(df_clean)} rows out")
    print("Label counts before:", dict(df_raw["label"].value_counts()))
    print("Label counts after: ", dict(df_clean["label"].value_counts()))
    print(f"Saved: {OUT_XLSX}")
    print(f"Saved: {OUT_CSV}")


def _selfcheck():
    df = pd.DataFrame({
        "fruit_id": ["AMAN_1", "AMAN_2", "BOSOK_1"],
        "scan_no": [1, 2, 3],
        "label": ["sehat", "normal", "anomali"],
    })
    out = clean(df)
    assert list(out["label"]) == ["normal", "normal", "anomali"]


if __name__ == "__main__":
    _selfcheck()
    main()
