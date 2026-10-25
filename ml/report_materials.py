"""Bahan laporan ML BuahSafe: gambar 300 dpi, tabel, Excel, Markdown, dan DOCX.

Membaca keluaran ml/evaluate_models.py (ml/output/, models/buahsafe_model.joblib)
sehingga semua angka di md/xlsx/docx berasal dari satu sumber yang sama.
Pemakaian: python ml/report_materials.py [folder_tujuan]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from docx import Document  # noqa: E402
from docx.shared import Cm  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import precision_score, recall_score, f1_score, roc_curve  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ML_OUT = ROOT / "ml" / "output"
DEST = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "bahan-laporan-ml"
FIG = DEST / "gambar"
FIG.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"figure.dpi": 100, "savefig.dpi": 300, "font.size": 10, "axes.grid": True, "grid.alpha": 0.3})
GREEN, RED, GREY = "#2e7d32", "#c62828", "#616161"

df = pd.read_csv(ROOT / "output" / "finalised" / "buahsafe_dataset_gabungan_final.csv")
res = json.loads((ML_OUT / "selection_result.json").read_text(encoding="utf-8"))
summary = pd.read_csv(ML_OUT / "nested_cv_summary.csv")
folds = pd.read_csv(ML_OUT / "nested_cv_per_fold.csv")
oof = pd.read_csv(ML_OUT / "nested_cv_oof_predictions.csv")
hold_pred = pd.read_csv(ML_OUT / "holdout_predictions.csv")
art = joblib.load(ROOT / "models" / "buahsafe_model.joblib")
CH = res["channels"]
WL = [int(c[2:]) for c in CH]
ALL18 = [c for c in df.columns if re.fullmatch(r"nm\d+", c)]
THR = res["threshold"]
H = res["holdout"]["threshold"]
best_oof = oof[(oof["model"] == res["model_name"]) & (oof["channels"] == res["channel_set"])]
hold = df[df["fruit_id"].isin(res["dataset"]["holdout_fruits"])].reset_index(drop=True)
y_hold = (hold["label"] == "anomali").astype(int).to_numpy()
pct = lambda v: f"{v * 100:.1f}%".replace(".", ",")  # noqa: E731
num = lambda v, d=3: f"{v:.{d}f}".replace(".", ",")  # noqa: E731


def save(fig, name: str) -> str:
    fig.tight_layout()
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)
    return f"gambar/{name}"


# ---------------- Gambar ----------------
figs: dict[str, str] = {}

fig, ax = plt.subplots(figsize=(8, 4.5))
wl18 = [int(c[2:]) for c in ALL18]
for label, color, name in (("normal", GREEN, "Normal"), ("anomali", RED, "Anomali")):
    part = df[df["label"] == label][ALL18]
    ax.plot(wl18, part.mean(), "-o", color=color, ms=4, label=f"{name} (n = {len(part)} scan)")
    ax.fill_between(wl18, part.mean() - part.std(), part.mean() + part.std(), color=color, alpha=0.15)
for w in (730, 810):
    ax.axvline(w, color=GREY, ls="--", lw=0.8)
ax.set_xlabel("Panjang gelombang (nm)")
ax.set_ylabel("Intensitas transmisi (satuan terkalibrasi sensor)")
ax.set_title("Rata-rata spektrum intensitas transmisi per kelas (± simpangan baku)")
ax.legend()
figs["spektrum"] = save(fig, "01_spektrum_intensitas_transmisi.png")

Xs = StandardScaler().fit_transform(df[ALL18])
pca = PCA(n_components=2).fit(Xs)
P = pca.transform(Xs)
fig, ax = plt.subplots(figsize=(6, 5))
for label, color, name in (("normal", GREEN, "Normal"), ("anomali", RED, "Anomali")):
    m = (df["label"] == label).to_numpy()
    ax.scatter(P[m, 0], P[m, 1], s=12, alpha=0.6, color=color, label=name)
ax.set_xlabel(f"Komponen utama 1 ({pca.explained_variance_ratio_[0] * 100:.1f}% variasi)")
ax.set_ylabel(f"Komponen utama 2 ({pca.explained_variance_ratio_[1] * 100:.1f}% variasi)")
ax.set_title("Sebaran 518 scan pada dua komponen utama (PCA, 18 kanal)")
ax.legend()
figs["pca"] = save(fig, "02_pca_18_kanal.png")

fig, ax = plt.subplots(figsize=(8.5, 4.5))
order = summary.sort_values(["channels", "model"])
labels = [f"{m}\n{c}" for m, c in zip(order["model"], order["channels"])]
x = np.arange(len(order))
for i, (metric, name) in enumerate((("accuracy", "Akurasi"), ("f1", "F1"), ("roc_auc", "ROC-AUC"))):
    ax.bar(x + (i - 1) * 0.27, order[f"{metric}_mean"], 0.27, yerr=order[f"{metric}_std"], capsize=2, label=name)
ax.set_xticks(x, labels, fontsize=8)
ax.set_ylim(0.4, 1.0)
ax.set_ylabel("Nilai rata-rata 5 lipatan luar")
ax.set_title("Perbandingan model, validasi silang bersarang per buah (± simpangan baku)")
ax.legend(ncol=3)
figs["perbandingan"] = save(fig, "03_perbandingan_model_nested_cv.png")

fig, ax = plt.subplots(figsize=(4.8, 4.2))
cm = np.array([[H["tn"], H["fp"]], [H["fn"], H["tp"]]])
ax.imshow(cm, cmap="Blues")
ax.grid(False)
for (i, j), v in np.ndenumerate(cm):
    ax.text(j, i, str(v), ha="center", va="center", fontsize=16, fontweight="bold",
            color="white" if v > cm.max() / 2 else "black")
ax.set_xticks([0, 1], ["Normal", "Anomali"])
ax.set_yticks([0, 1], ["Normal", "Anomali"])
ax.set_xlabel("Prediksi model")
ax.set_ylabel("Kondisi sebenarnya (hasil belah)")
ax.set_title(f"Confusion matrix data uji independen\n({len(hold)} scan, ambang {num(THR, 2)})")
figs["cm"] = save(fig, "04_confusion_matrix_holdout.png")

fig, ax = plt.subplots(figsize=(5.2, 5))
prob_hold = hold_pred["prob_anomali"].to_numpy()
for y, p, name, color in ((best_oof["y"], best_oof["prob"], f"Validasi silang (AUC {num(res['nested_cv_oof_at_threshold']['roc_auc'])})", "#1565c0"),
                          (y_hold, prob_hold, f"Uji independen (AUC {num(H['roc_auc'])})", RED)):
    fpr, tpr, _ = roc_curve(y, p)
    ax.plot(fpr, tpr, color=color, lw=2, label=name)
ax.plot([0, 1], [0, 1], "k--", lw=1, label="Tebakan acak")
ax.set_xlabel("Laju positif palsu (buah sehat dikira anomali)")
ax.set_ylabel("Laju positif benar (recall anomali)")
ax.set_title(f"Kurva ROC {res['model_name']} {res['channel_set']}")
ax.legend(loc="lower right", fontsize=8)
figs["roc"] = save(fig, "05_kurva_roc.png")

pi = permutation_importance(art["pipeline"], hold[CH].to_numpy(), y_hold, scoring="roc_auc", n_repeats=30, random_state=42)
imp = pd.DataFrame({"kanal": [f"{w} nm" for w in WL], "penurunan_auc": pi.importances_mean, "sd": pi.importances_std})
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(imp["kanal"], imp["penurunan_auc"], yerr=imp["sd"], capsize=2,
       color=[RED if w in (730, 810) else "#1565c0" for w in WL])
ax.set_ylabel("Penurunan ROC-AUC saat kanal diacak")
ax.set_title("Kepentingan kanal (permutation importance, data uji independen)")
plt.setp(ax.get_xticklabels(), rotation=60, fontsize=8)
figs["kanal"] = save(fig, "06_kepentingan_kanal.png")

ts = np.round(np.arange(0.05, 0.951, 0.01), 2)
yo, po = best_oof["y"].to_numpy(), best_oof["prob"].to_numpy()
curve = pd.DataFrame({"ambang": ts,
                      "presisi": [precision_score(yo, po >= t, zero_division=0) for t in ts],
                      "recall": [recall_score(yo, po >= t) for t in ts],
                      "f1": [f1_score(yo, po >= t) for t in ts],
                      # bagian buah sehat yang dicap anomali (dibuang/diperiksa ulang)
                      "alarm_palsu": [float(((po >= t) & (yo == 0)).sum() / max((yo == 0).sum(), 1)) for t in ts]})
fig, ax = plt.subplots(figsize=(7, 4))
for col, color in (("presisi", "#1565c0"), ("recall", RED), ("f1", GREY)):
    ax.plot(curve["ambang"], curve[col], color=color, lw=2, label=col.capitalize() if col != "f1" else "F1")
ax.axvline(THR, color="black", ls="--", lw=1, label=f"Ambang terpilih {num(THR, 2)}")
ax.axhline(res["recall_target"], color=RED, ls=":", lw=1, label=f"Target recall {pct(res['recall_target'])}")
ax.set_xlabel("Ambang probabilitas anomali")
ax.set_ylabel("Nilai (prediksi out-of-fold)")
ax.set_title("Pemilihan ambang keputusan")
ax.legend(fontsize=8)
figs["ambang"] = save(fig, "07_pemilihan_ambang.png")

per_fruit = hold_pred.groupby("fruit_id").agg(label=("label", "first"), rata_prob=("prob_anomali", "mean"),
                                              scan_anomali=("prediksi", lambda s: int((s == "anomali").sum())),
                                              jumlah_scan=("prediksi", "size")).reset_index()
per_fruit["putusan_rata_rata"] = np.where(per_fruit["rata_prob"] >= THR, "anomali", "normal")
fruit_correct = int((per_fruit["putusan_rata_rata"] == per_fruit["label"]).sum())
fig, ax = plt.subplots(figsize=(8, 4))
for _, r in per_fruit.iterrows():
    color = RED if r["label"] == "anomali" else GREEN
    rows_f = hold_pred[hold_pred["fruit_id"] == r["fruit_id"]]
    ax.scatter([r["fruit_id"]] * len(rows_f), rows_f["prob_anomali"], color=color, alpha=0.35, s=14)
    ax.scatter(r["fruit_id"], r["rata_prob"], color=color, marker="D", s=50, edgecolor="black")
ax.axhline(THR, color="black", ls="--", lw=1)
ax.set_ylabel("Probabilitas anomali")
ax.set_title("Per buah uji independen: titik = tiap sisi, belah ketupat = rata-rata 8 sisi")
plt.setp(ax.get_xticklabels(), rotation=60, fontsize=8)
figs["per_buah"] = save(fig, "08_probabilitas_per_buah.png")

# ---------------- Excel ----------------
fruits = df.groupby("fruit_id")["label"].first()
with pd.ExcelWriter(DEST / "hasil_ml.xlsx") as xw:
    summary.round(4).to_excel(xw, sheet_name="ringkasan_nested_cv", index=False)
    folds.round(4).to_excel(xw, sheet_name="per_lipatan_nested_cv", index=False)
    pd.DataFrame([{"ambang": THR, **res["holdout"]["threshold"]}, {"ambang": 0.5, **res["holdout"]["default_0.5"]}]).round(4).to_excel(xw, sheet_name="uji_independen", index=False)
    hold_pred.to_excel(xw, sheet_name="prediksi_per_scan_holdout", index=False)
    per_fruit.round(4).to_excel(xw, sheet_name="prediksi_per_buah_holdout", index=False)
    imp.round(4).to_excel(xw, sheet_name="kepentingan_kanal", index=False)
    curve.round(4).to_excel(xw, sheet_name="kurva_ambang_oof", index=False)
    pd.DataFrame({"fruit_id": fruits.index, "label": fruits.values,
                  "bagian": ["uji independen" if f in res["dataset"]["holdout_fruits"] else "latih/validasi" for f in fruits.index]}).to_excel(xw, sheet_name="pembagian_buah", index=False)

# ---------------- Markdown ----------------
def table(frame: pd.DataFrame) -> str:
    head = "| " + " | ".join(frame.columns) + " |\n|" + "---|" * len(frame.columns) + "\n"
    return head + "".join("| " + " | ".join(str(v) for v in row) + " |\n" for row in frame.itertuples(index=False))


comp = summary.copy()
comp_tbl = pd.DataFrame({
    "Model": comp["model"], "Kanal": comp["channels"],
    "Akurasi": [f"{pct(m)} ± {pct(s)}" for m, s in zip(comp["accuracy_mean"], comp["accuracy_std"])],
    "Presisi": [pct(v) for v in comp["precision_mean"]],
    "Recall": [pct(v) for v in comp["recall_mean"]],
    "F1": [f"{num(m)} ± {num(s)}" for m, s in zip(comp["f1_mean"], comp["f1_std"])],
    "ROC-AUC": [num(v) for v in comp["roc_auc_mean"]],
})
O = res["nested_cv_oof_at_threshold"]
D = res["holdout"]["default_0.5"]
eval_tbl = pd.DataFrame({
    "Metrik": ["Akurasi", "Presisi (anomali)", "Recall/sensitivitas (anomali)", "Spesifisitas (normal)", "F1", "ROC-AUC"],
    f"Validasi silang, ambang {num(THR, 2)}": [num(O[k]) if k in ("roc_auc", "f1") else pct(O[k]) for k in ["accuracy", "precision", "recall", "specificity", "f1", "roc_auc"]],
    f"Uji independen, ambang {num(THR, 2)}": [num(H[k]) if k in ("roc_auc", "f1") else pct(H[k]) for k in ["accuracy", "precision", "recall", "specificity", "f1", "roc_auc"]],
    "Uji independen, ambang 0,50": [num(D[k]) if k in ("roc_auc", "f1") else pct(D[k]) for k in ["accuracy", "precision", "recall", "specificity", "f1", "roc_auc"]],
})
trade = curve[curve["ambang"].isin(np.round(np.arange(0.20, 0.501, 0.05), 2))]
trade_tbl = pd.DataFrame({
    "Ambang": [num(t, 2) for t in trade["ambang"]],
    "Buah busuk tertangkap (recall)": [pct(v) for v in trade["recall"]],
    "Buah sehat ikut ke keranjang merah": [pct(v) for v in trade["alarm_palsu"]],
    "Presisi": [pct(v) for v in trade["presisi"]],
})
fruit_tbl = per_fruit.assign(rata_prob=per_fruit["rata_prob"].map(num),
                             scan_anomali=per_fruit["scan_anomali"].astype(str) + "/" + per_fruit["jumlah_scan"].astype(str))[
    ["fruit_id", "label", "scan_anomali", "rata_prob", "putusan_rata_rata"]]
fruit_tbl.columns = ["ID buah", "Kondisi sebenarnya", "Sisi diputus anomali", "Rata-rata prob. anomali", "Putusan dari rata-rata"]
anom_f = per_fruit[per_fruit["label"] == "anomali"]
norm_f = per_fruit[per_fruit["label"] == "normal"]
top = imp.sort_values("penurunan_auc", ascending=False).head(4)

md = f"""# Bahan hasil machine learning BuahSafe

Dibuat otomatis oleh `buahsafe-web-capture/ml/report_materials.py` dari hasil `ml/evaluate_models.py` (seed 42). Semua angka di berkas ini, `hasil_ml.xlsx`, dan `HASIL_ML.docx` berasal dari sumber yang sama. Ini bahan, bukan naskah bab: tim memilih dan menulis ulang sesuai gaya laporan.

## 1. Data

- {res['dataset']['scans']} scan dari {res['dataset']['fruits']} buah jambu kristal ({int((fruits == 'normal').sum())} normal, {int((fruits == 'anomali').sum())} anomali), 8 sisi per buah (rotasi 45°), kecuali satu buah (AMAN_010) yang hanya 6 sisi.
- Fitur: intensitas transmisi terkalibrasi sensor AS7265x pada 18 kanal 410–940 nm. Label dari pembelahan buah setelah gejala kerusakan muncul.
- Pembagian per buah, bukan per scan, supaya sisi lain dari buah yang sama tidak bocor ke data uji. {res['dataset']['dev_fruits']} buah ({len(df) - len(hold)} scan) untuk pelatihan dan pemilihan model; {len(res['dataset']['holdout_fruits'])} buah ({len(hold)} scan; {int((hold.groupby('fruit_id')['label'].first() == 'normal').sum())} normal, {int((hold.groupby('fruit_id')['label'].first() == 'anomali').sum())} anomali) disisihkan sebagai **data uji independen** dan baru dipakai sekali di akhir.
- Pra-pengolahan: standardisasi z-score (StandardScaler) untuk LR dan SVM; RF tanpa standardisasi. Tidak ada smoothing, SNV, MSC, atau Savitzky-Golay.

![Rata-rata spektrum]({figs['spektrum']})

*Gambar A. Rata-rata spektrum intensitas transmisi jambu normal dan anomali (± simpangan baku). Garis putus-putus menandai 730 dan 810 nm.*

![PCA]({figs['pca']})

*Gambar B. Proyeksi 518 scan ke dua komponen utama. Kedua kelas bertumpang tindih, sehingga diperlukan pemisah non-linear.*

## 2. Metode pemilihan model

- Kandidat: Logistic Regression (LR), Support Vector Machine kernel RBF (SVM), dan Random Forest (RF), masing-masing pada 6 kanal (610, 680, 730, 760, 810, 860 nm) dan 18 kanal.
- Validasi silang bersarang per buah (StratifiedGroupKFold): lipatan luar 5 untuk menilai, lipatan dalam 4 untuk mencari hiperparameter (GridSearchCV, skor F1). Dengan cara ini angka penilaian tidak ikut dipakai saat tuning.
- Kriteria: F1 tertinggi pada lipatan luar. Ambang probabilitas anomali dipilih dari prediksi out-of-fold sebagai ambang tertinggi yang masih memberi recall anomali ≥ {pct(res['recall_target'])}. Alasannya, buah busuk yang lolos ke keranjang hijau lebih merugikan daripada buah sehat yang diperiksa ulang.
- Model akhir dilatih ulang pada seluruh data pelatihan dengan hiperparameter terbaik ({', '.join(f'{k.split("__")[1]} = {v}' for k, v in res['params'].items())}), lalu diuji sekali pada data uji independen.

## 3. Perbandingan model (validasi silang bersarang, ambang 0,50)

Tabel A. Rata-rata ± simpangan baku 5 lipatan luar, diurutkan menurut F1.

{table(comp_tbl)}
![Perbandingan model]({figs['perbandingan']})

*Gambar C. Akurasi, F1, dan ROC-AUC tiap kandidat.*

Model terpilih: **{res['model_name']} {res['channel_set']}** (F1 {num(res['nested_cv_mean']['f1'])}). Selisihnya dengan SVM 6 kanal (F1 {num(float(comp[(comp['model'] == 'SVM (RBF)') & (comp['channels'] == '6 kanal')]['f1_mean'].iloc[0]))}) lebih kecil dari simpangan baku antarlipatan, jadi keunggulan 18 kanal belum dapat dinyatakan signifikan. LR konsisten paling rendah, sesuai tumpang tindih kelas pada Gambar B.

## 4. Ambang keputusan

![Pemilihan ambang]({figs['ambang']})

*Gambar D. Presisi, recall, dan F1 terhadap ambang (prediksi out-of-fold). Ambang {num(THR, 2)} adalah ambang tertinggi dengan recall anomali ≥ {pct(res['recall_target'])}.*

Tabel A2. Tukar-ganti ambang untuk **satu scan per buah** (conveyor), dari prediksi out-of-fold 52 buah latih. Ambang lebih rendah menangkap lebih banyak buah busuk, dengan imbalan lebih banyak buah sehat masuk keranjang merah.

{table(trade_tbl)}
Ambang produksi saat ini {num(THR, 2)}. Pilihan ambang adalah keputusan bisnis mitra (biaya buah busuk lolos vs buah sehat terbuang), lalu sebaiknya diverifikasi ulang dengan data conveyor.

## 5. Hasil pada data uji independen

Tabel B. Kinerja model terpilih.

{table(eval_tbl)}
Pada data uji independen, ambang {num(THR, 2)} memberi recall {pct(H['recall'])}. Angka ini **di bawah** target {pct(res['recall_target'])} yang tercapai pada validasi silang ({pct(O['recall'])}). Data uji hanya {len(res['dataset']['holdout_fruits'])} buah, jadi satu buah sulit ({anom_f.sort_values('rata_prob').iloc[0]['fruit_id']}, hanya {int(anom_f.sort_values('rata_prob').iloc[0]['scan_anomali'])} dari 8 sisi terdeteksi) sudah menggeser recall per scan secara nyata.

![Confusion matrix]({figs['cm']})

*Gambar E. Confusion matrix data uji independen ({len(hold)} scan): {H['tn']} normal benar, {H['fp']} normal dikira anomali, {H['fn']} anomali lolos sebagai normal, {H['tp']} anomali tertangkap.*

![ROC]({figs['roc']})

*Gambar F. Kurva ROC validasi silang (AUC {num(O['roc_auc'])}) dan data uji independen (AUC {num(H['roc_auc'])}).*

### Keputusan per buah (rata-rata 8 sisi)

Tabel C. Probabilitas anomali dirata-ratakan dari semua sisi satu buah, lalu dibandingkan dengan ambang yang sama.

{table(fruit_tbl)}
Dengan merata-ratakan semua sisi, **{fruit_correct} dari {len(per_fruit)} buah** diputus benar ({int((norm_f['putusan_rata_rata'] == 'normal').sum())}/{len(norm_f)} normal, {int((anom_f['putusan_rata_rata'] == 'anomali').sum())}/{len(anom_f)} anomali). Ini temuan analisis: kerusakan internal tidak selalu berada di jalur cahaya sisi yang dipindai. Alat conveyor memindai **satu kali per buah** pada sisi yang kebetulan menghadap sensor, sehingga angka yang berlaku di lapangan adalah angka per scan pada Tabel B, bukan angka per buah ini.

![Per buah]({figs['per_buah']})

*Gambar G. Probabilitas anomali tiap sisi (titik) dan rata-ratanya (belah ketupat) untuk 13 buah uji independen.*

## 6. Kepentingan kanal

![Kepentingan kanal]({figs['kanal']})

*Gambar H. Penurunan ROC-AUC ketika nilai satu kanal diacak (30 ulangan, data uji independen). Batang merah = 730 dan 810 nm.*

Empat kanal paling berpengaruh: {', '.join(f"{k} ({num(v)})" for k, v in zip(top['kanal'], top['penurunan_auc']))}.

## 7. Kinerja di server

- Alat conveyor: sensor PIR memicu lampu halogen dan satu pengukuran saat buah lewat; hasil tampil di antrean web operator di ujung belt dan di LCD + buzzer alat.
- Model berjalan di server HP t530 (AMD GX-215JJ 2 inti 1,5 GHz, Python 3.14, scikit-learn 1.9.0). Waktu inferensi 16 ms per scan; satu siklus scan lewat internet sekitar 4–5 detik, terutama karena pemanasan lampu halogen 3 detik.
- Prediksi server identik dengan prediksi komputer pengembang untuk 20 scan uji.
- Model demo saat ini dilatih dengan 80% buah agar data uji independen tetap bersih. Sebelum dipakai dengan alat asli di mitra, model dilatih ulang dengan seluruh 65 buah (`python ml/evaluate_models.py --full`).

## 8. Keterbatasan

- Jumlah buah kecil (65; uji independen 13), sehingga selang ketidakpastian lebar.
- Label "anomali" menggabungkan berbagai penyebab kerusakan (larva lalat buah, busuk, memar), bukan hanya infestasi tahap awal.
- Intensitas adalah nilai mentah terkalibrasi sensor tanpa koreksi referensi putih/gelap, sehingga peka terhadap perubahan lampu dan jarak.
- Seluruh data latih diambil dengan buah **diam** dan diputar manual 45°. Alat sebenarnya memindai buah yang **bergerak** di belt conveyor sekali lewat (dipicu sensor PIR), sehingga jarak, posisi, dan waktu pengukuran berbeda. Akurasi pada conveyor belum terbukti sampai data conveyor berlabel terkumpul dan model dilatih ulang (`ml/evaluate_models.py --data`).
- Belum ada uji lapangan dengan alat di lokasi mitra.
- Recall per scan pada data uji independen ({pct(H['recall'])}) belum mencapai target {pct(res['recall_target'])}. Pilihan untuk satu scan per buah: menurunkan ambang (Tabel A2) dan menambah data conveyor.
"""
(DEST / "HASIL_ML.md").write_text(md, encoding="utf-8")


# ---------------- DOCX (dari Markdown yang sama) ----------------
def md_to_docx(text: str, base: Path, out: Path) -> None:
    doc = Document()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].startswith("|"):
                block.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            rows = [r for r in block if not set("".join(r)) <= {"-"}]
            t = doc.add_table(rows=len(rows), cols=len(rows[0]))
            t.style = "Table Grid"
            for r, cells in enumerate(rows):
                for c, val in enumerate(cells):
                    t.cell(r, c).text = val.replace("**", "")
            continue
        m = re.match(r"!\[.*?\]\((.+?)\)", line)
        if m:
            doc.add_picture(str(base / m.group(1)), width=Cm(15))
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            doc.add_heading(line.lstrip("# "), level=min(level, 3))
        elif line.startswith("- "):
            add_runs(doc.add_paragraph(style="List Bullet"), line[2:])
        elif line.strip():
            add_runs(doc.add_paragraph(), line)
        i += 1
    doc.save(out)


def add_runs(par, text: str) -> None:
    for part in re.split(r"(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("*"):
            par.add_run(part[1:-1]).italic = True
        elif part.startswith("`"):
            par.add_run(part[1:-1]).font.name = "Consolas"
        else:
            par.add_run(part)


md_to_docx(md, DEST, DEST / "HASIL_ML.docx")


# ---------------- Diagram untuk dokumen penjelasan awam ----------------
def flow(steps: list[tuple[str, str]], name: str, title: str, per_row: int = 4) -> None:
    rows = (len(steps) + per_row - 1) // per_row
    fig, ax = plt.subplots(figsize=(11, 2.6 * rows))
    ax.set_xlim(0, per_row)
    ax.set_ylim(-rows, 0.35)
    ax.axis("off")
    pos = []
    for i, (head, body) in enumerate(steps):
        r, c = divmod(i, per_row)
        c = c if r % 2 == 0 else per_row - 1 - c  # alur zig-zag agar panah pendek
        x, y = c + 0.5, -r - 0.45
        pos.append((x, y))
        ax.add_patch(matplotlib.patches.FancyBboxPatch((x - 0.42, y - 0.38), 0.84, 0.76, boxstyle="round,pad=0.02",
                                                       fc="#e8f5e9" if i % 2 == 0 else "#e3f2fd", ec="#455a64"))
        ax.text(x, y + 0.2, f"{i + 1}. {head}", ha="center", va="center", fontsize=9, fontweight="bold")
        ax.text(x, y - 0.08, body.replace(" | ", "\n"), ha="center", va="center", fontsize=7.5)
    for (x1, y1), (x2, y2) in zip(pos, pos[1:]):
        dx, dy = (0.43 if x2 > x1 else -0.43 if x2 < x1 else 0), (0 if y1 == y2 else -0.39)
        ax.annotate("", xy=(x2 - dx, y2 - dy if dy else y2), xytext=(x1 + dx, y1 + dy),
                    arrowprops=dict(arrowstyle="->", color="#37474f", lw=1.5))
    ax.set_title(title, fontsize=11, fontweight="bold")
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)


flow([("Masuk belt", "Buah diletakkan di conveyor | yang terus berjalan"),
      ("Terdeteksi", "Sensor PIR memicu | lampu halogen menyala"),
      ("Diukur", "AS7265x membaca cahaya | tembus 18 warna, sekali lewat"),
      ("Dikirim", "ESP32 mengirim lewat WiFi | mitra dan internet (HTTPS)"),
      ("Dinilai", "Server mini PC menjalankan | model ML (16 ms)"),
      ("Disimpan", "Hasil masuk database | di server (backup harian)"),
      ("Ditampilkan", "Antrean web + LCD + bunyi | dengan nomor urut buah"),
      ("Dipilah", "Operator di ujung belt: | keranjang HIJAU atau MERAH")],
     "09_alur_satu_buah.png", "Perjalanan satu buah jambu di sistem BuahSafe")
flow([("Kumpulkan", "65 buah dipindai | 8 sisi = 518 scan"),
      ("Beri kunci jawaban", "Buah disimpan sampai | rusak tampak, lalu dibelah"),
      ("Sisihkan ujian", "13 buah disimpan untuk | ujian akhir, tidak dilihat"),
      ("Latih & bandingkan", "52 buah: 6 kandidat model | dinilai bergiliran per buah"),
      ("Pilih", "F1 tertinggi: | SVM 18 kanal"),
      ("Atur ambang", "Ambang 0,45 agar buah busuk | lebih jarang lolos"),
      ("Ujian akhir", "Diuji sekali pada | 13 buah tersimpan"),
      ("Pasang", "Model dipasang di server; | kelak dilatih ulang 65 buah")],
     "10_alur_melatih_model.png", "Bagaimana model BuahSafe dilatih dan diuji")

penjelasan = DEST / "PENJELASAN_ALUR_BUAHSAFE.md"
if penjelasan.exists():
    md_to_docx(penjelasan.read_text(encoding="utf-8"), DEST, DEST / "PENJELASAN_ALUR_BUAHSAFE.docx")
print(f"Bahan laporan ditulis ke {DEST} ({len(figs)} gambar, xlsx, md, docx)")
