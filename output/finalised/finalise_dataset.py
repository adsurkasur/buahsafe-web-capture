"""Gabungkan batch 29/08 + batch 3/09 (finalised), perbaiki ID, normalisasi label, seragamkan ID & scan_no.
Default: dry-run (hanya laporan). Tulis file: tambahkan argumen --write
"""
import os
import sys
import pandas as pd

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B1 = os.path.join(OUT, "fixed", "buahsafe_dataset_gabungan_29082026.xlsx")
B2 = os.path.join(OUT, "finalised", "buahsafe_dataset_bosok-23-31_aman-18-34.xlsx")

# scan pertama (rotasi a) yang ID-nya lupa diganti -> ID buah berikutnya (dikunci pakai timestamp)
ID_FIX = {"2026-09-03T20:28:03.975": "AMAN_20", "2026-09-03T20:31:25.964": "AMAN_21"}
EXPECTED_SHORT = {"AMAN_010"}  # memang hanya 6 scan di data mentah

b1, b2 = pd.read_excel(B1), pd.read_excel(B2).drop(columns=["rotasi_sensor"])
assert list(b1.columns) == list(b2.columns)
df = pd.concat([b1, b2], ignore_index=True)
df["timestamp"] = df["timestamp"].astype(str).str.replace(",", ".", regex=False)
df["_t"] = pd.to_datetime(df["timestamp"], format="mixed")
df = df.sort_values("_t").reset_index(drop=True)

hit = df["timestamp"].isin(ID_FIX)
assert hit.sum() == len(ID_FIX), "baris ID_FIX tidak ditemukan"
before = df.loc[hit, ["timestamp", "fruit_id", "rotasi_buah"]].copy()
df.loc[hit, "fruit_id"] = df.loc[hit, "timestamp"].map(ID_FIX)

df["label"] = df["label"].replace({"sehat": "normal"})
pre, num = df["fruit_id"].str.extract(r"^([A-Z]+)_(\d+)$").T.values
df["fruit_id"] = [f"{p}_{int(n):03d}" for p, n in zip(pre, num)]
df["scan_no"] = range(1, len(df) + 1)
df = df.drop(columns="_t")

# validasi
assert df["label"].isin(["normal", "anomali"]).all()
assert (df["fruit_id"].str.startswith("AMAN") == (df["label"] == "normal")).all()
assert not df.duplicated(["fruit_id", "rotasi_buah"]).any()
g = df.groupby("fruit_id", sort=False).agg(n=("label", "size"), rot=("rotasi_buah", "".join))
bad = g[(g.rot != "abcdefgh") & ~g.index.isin(EXPECTED_SHORT)]
assert bad.empty, bad
# ID harus kontigu dalam urutan waktu (tidak ada buah yang "terputus" oleh buah lain)
assert (df["fruit_id"] != df["fruit_id"].shift()).sum() == df["fruit_id"].nunique()

print("Perbaikan ID:\n", before.assign(baru=before.timestamp.map(ID_FIX)).to_string(index=False))
print(f"\nTotal {len(df)} baris, {df.fruit_id.nunique()} objek | label {df.label.value_counts().to_dict()}")
print("Objek != 8 scan:", g[g.n != 8].to_dict("index"))

if "--write" in sys.argv:
    base = os.path.join(OUT, "finalised", "buahsafe_dataset_gabungan_final")
    df.to_csv(base + ".csv", index=False)
    df.to_excel(base + ".xlsx", index=False)
    print("Ditulis:", base + ".csv/.xlsx")
