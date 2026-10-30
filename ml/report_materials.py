"""Bahan laporan ML BuahSafe: gambar 300 dpi, tabel, Excel, Markdown, dan DOCX.

Membaca keluaran ml/evaluate_models.py (ml/output/, models/buahsafe_model.joblib)
sehingga semua angka di md/xlsx/docx berasal dari satu sumber yang sama.
Pemakaian: python ml/report_materials.py [folder_tujuan]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from md_docx import md_to_docx  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import precision_score, recall_score, f1_score, roc_curve  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ML_OUT = ROOT / "ml" / "output"
DEST = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "laporan-akhir" / "sumber" / "bahan-laporan-ml"
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
THR = res["threshold"]
H = res["holdout"]["threshold"]
best_oof = oof[(oof["model"] == res["model_name"]) & (oof["channels"] == res["channel_set"])]
hold = df[df["fruit_id"].isin(res["dataset"]["holdout_fruits"])].reset_index(drop=True)
y_hold = (hold["label"] == "anomali").astype(int).to_numpy()
INFER_MS = "1,3"  # diukur di server t530 (predictor.predict, rata-rata 50 kali, model 6 kanal)
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
for label, color, name in (("normal", GREEN, "Normal"), ("anomali", RED, "Anomali")):
    part = df[df["label"] == label][CH]
    ax.plot(WL, part.mean(), "-o", color=color, ms=4, label=f"{name} (n = {len(part)} scan)")
    ax.fill_between(WL, part.mean() - part.std(), part.mean() + part.std(), color=color, alpha=0.15)
for w in (730, 810):
    ax.axvline(w, color=GREY, ls="--", lw=0.8)
ax.set_xlabel("Panjang gelombang (nm)")
ax.set_ylabel("Intensitas transmisi (satuan terkalibrasi sensor)")
ax.set_title(f"Rata-rata intensitas transmisi {len(CH)} kanal NIR per kelas (± simpangan baku)")
ax.legend()
figs["spektrum"] = save(fig, "01_spektrum_intensitas_transmisi.png")

Xs = StandardScaler().fit_transform(df[CH])
pca = PCA(n_components=2).fit(Xs)
P = pca.transform(Xs)
fig, ax = plt.subplots(figsize=(6, 5))
for label, color, name in (("normal", GREEN, "Normal"), ("anomali", RED, "Anomali")):
    m = (df["label"] == label).to_numpy()
    ax.scatter(P[m, 0], P[m, 1], s=12, alpha=0.6, color=color, label=name)
ax.set_xlabel(f"Komponen utama 1 ({pca.explained_variance_ratio_[0] * 100:.1f}% variasi)")
ax.set_ylabel(f"Komponen utama 2 ({pca.explained_variance_ratio_[1] * 100:.1f}% variasi)")
ax.set_title(f"Sebaran {len(df)} scan pada dua komponen utama (PCA, {res['channel_set']} NIR)")
ax.legend()
for old in FIG.glob("02_pca_*.png"):
    old.unlink()
figs["pca"] = save(fig, f"02_pca_{res['channel_set'].replace(' ', '_')}.png")

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


# Kanal utama (NIR) di atas, pembanding 18 kanal di bawah; masing-masing urut F1
comp = summary.assign(_main=summary["channels"] != res["channel_set"]).sort_values(["_main", "f1_mean"], ascending=[True, False])
comp_tbl = pd.DataFrame({
    "Model": comp["model"],
    "Kanal": [f"{c} NIR (utama)" if c == res["channel_set"] else f"{c} (pembanding)" for c in comp["channels"]],
    "Akurasi": [f"{pct(m)} ± {pct(s)}" for m, s in zip(comp["accuracy_mean"], comp["accuracy_std"])],
    "Presisi": [pct(v) for v in comp["precision_mean"]],
    "Recall": [pct(v) for v in comp["recall_mean"]],
    "F1": [f"{num(m)} ± {num(s)}" for m, s in zip(comp["f1_mean"], comp["f1_std"])],
    "ROC-AUC": [num(v) for v in comp["roc_auc_mean"]],
})
best18 = comp[comp["channels"] == "18 kanal"].iloc[0]
res_std = float(comp[(comp["model"] == res["model_name"]) & (comp["channels"] == res["channel_set"])]["f1_std"].iloc[0])
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
top = imp.sort_values("penurunan_auc", ascending=False).head(3)

md = f"""# Hasil pembelajaran mesin BuahSafe

Dokumen ini dibangkitkan otomatis oleh `buahsafe-web-capture/ml/report_materials.py` dari keluaran `ml/evaluate_models.py` (seed 42). Seluruh angka dalam dokumen ini, `hasil_ml.xlsx`, dan `HASIL_ML.docx` bersumber dari berkas yang sama. Dokumen ini merupakan bahan, bukan naskah bab; tim memilih dan menyesuaikannya dengan gaya laporan.

## 1. Data

- Data terdiri atas {res['dataset']['scans']} pemindaian dari {res['dataset']['fruits']} buah jambu kristal ({int((fruits == 'normal').sum())} normal, {int((fruits == 'anomali').sum())} anomali). Setiap buah dipindai pada 8 sisi dengan rotasi 45°, kecuali satu buah (AMAN_010) yang hanya 6 sisi.
- Fitur berupa intensitas transmisi terkalibrasi pada **{len(CH)} kanal NIR ({', '.join(str(w) for w in WL)} nm)**. Kanal ini sama dengan kanal sensor NIR AS7263 yang direncanakan; karena sensor tersebut rusak, pengukuran memakai AS7265x yang chip AS72651-nya membaca keenam kanal yang sama. AS7265x juga merekam kanal cahaya tampak, tetapi kanal tersebut tidak dipakai. Salah satunya, 485 nm, bernilai 0 pada {int((df['nm485'] == 0).sum())} dari {len(df)} pemindaian, sehingga tidak layak menjadi fitur.
- Label ditetapkan dari hasil pembelahan buah setelah gejala kerusakan muncul.
- Data dibagi per buah, bukan per pemindaian, agar sisi lain dari buah yang sama tidak masuk ke data uji. Pemisahan kelompok ini mencegah kebocoran data (Kapoor dan Narayanan, 2023; Roberts *et al.*, 2017). Sebanyak {res['dataset']['dev_fruits']} buah ({len(df) - len(hold)} pemindaian) dipakai untuk pelatihan dan pemilihan model, sedangkan {len(res['dataset']['holdout_fruits'])} buah ({len(hold)} pemindaian; {int((hold.groupby('fruit_id')['label'].first() == 'normal').sum())} normal, {int((hold.groupby('fruit_id')['label'].first() == 'anomali').sum())} anomali) disisihkan sebagai **data uji independen** yang hanya dipakai sekali pada tahap akhir.
- Pra-pengolahan hanya berupa standardisasi z-score (StandardScaler) untuk LR dan SVM; RF dipakai tanpa standardisasi. Penghalusan, SNV, MSC, dan Savitzky-Golay tidak dipakai.

![Rata-rata spektrum]({figs['spektrum']})

*Gambar A. Rata-rata intensitas transmisi {len(CH)} kanal NIR jambu normal dan anomali (± simpangan baku). Garis putus-putus menandai 730 dan 810 nm.*

![PCA]({figs['pca']})

*Gambar B. Proyeksi {res['dataset']['scans']} pemindaian ({len(CH)} kanal NIR) pada dua komponen utama. Kedua kelas bertumpang tindih, sehingga diperlukan pemisah nonlinear.*

## 2. Metode pemilihan model

- Kandidat terdiri atas Logistic Regression (LR), Support Vector Machine kernel RBF (SVM; Cortes dan Vapnik, 1995), dan Random Forest (RF; Breiman, 2001), masing-masing dilatih pada {len(CH)} kanal NIR. Sebagai pembanding, ketiganya juga dinilai pada 18 kanal AS7265x untuk melihat apakah kanal cahaya tampak menambah informasi.
- Penilaian memakai validasi silang bersarang per buah (StratifiedGroupKFold): 5 lipatan luar untuk menilai kinerja dan 4 lipatan dalam untuk mencari hiperparameter (GridSearchCV, skor F1). Pemisahan ini mencegah bias optimistis akibat pemilihan hiperparameter pada data penilaian (Varma dan Simon, 2006).
- Model dipilih menurut F1 tertinggi pada lipatan luar di antara kandidat {len(CH)} kanal NIR, karena akurasi saja tidak membedakan jenis kesalahan (Chicco dan Jurman, 2020). Ambang probabilitas anomali dipilih dari prediksi out-of-fold sebagai ambang tertinggi yang masih memberi recall anomali ≥ {pct(res['recall_target'])}. Dasarnya, biaya buah busuk yang lolos ke keranjang hijau lebih besar daripada biaya pemeriksaan ulang buah sehat, dan titik operasi sebaiknya mengikuti perbandingan biaya kesalahan (Provost dan Fawcett, 2001).
- Model akhir dilatih ulang pada seluruh data pelatihan dengan hiperparameter terbaik ({', '.join(f'{k.split("__")[1]} = {v}' for k, v in res['params'].items())}), lalu diuji sekali pada data uji independen.

## 3. Perbandingan model (validasi silang bersarang, ambang 0,50)

Tabel A. Rata-rata ± simpangan baku 5 lipatan luar. Kandidat utama {len(CH)} kanal NIR di atas, pembanding 18 kanal di bawah, masing-masing diurutkan menurut F1.

{table(comp_tbl)}
![Perbandingan model]({figs['perbandingan']})

*Gambar C. Akurasi, F1, dan ROC-AUC tiap kandidat.*

Model terpilih adalah **{res['model_name']} {res['channel_set']} NIR** (F1 {num(res['nested_cv_mean']['f1'])} ± {num(res_std)}). Pembanding terbaik pada 18 kanal mencapai F1 {num(best18['f1_mean'])} ± {num(best18['f1_std'])}; selisihnya lebih kecil daripada simpangan baku antarlipatan, sehingga penambahan kanal cahaya tampak tidak memberi peningkatan yang bermakna. LR konsisten paling rendah, sesuai dengan tumpang tindih kelas pada Gambar B.

## 4. Ambang keputusan

![Pemilihan ambang]({figs['ambang']})

*Gambar D. Presisi, recall, dan F1 terhadap ambang (prediksi out-of-fold). Ambang {num(THR, 2)} adalah ambang tertinggi dengan recall anomali ≥ {pct(res['recall_target'])}.*

Tabel A2. Pertukaran ambang untuk **satu pemindaian per buah** (conveyor), dari prediksi out-of-fold {res['dataset']['dev_fruits']} buah latih. Ambang yang lebih rendah menangkap lebih banyak buah busuk, dengan konsekuensi lebih banyak buah sehat masuk keranjang merah.

{table(trade_tbl)}
Ambang produksi saat ini {num(THR, 2)}. Penetapan ambang merupakan keputusan bisnis mitra berdasarkan biaya buah busuk yang lolos dibandingkan dengan buah sehat yang terbuang, dan perlu diverifikasi ulang dengan data conveyor.

## 5. Hasil pada data uji independen

Tabel B. Kinerja model terpilih per pemindaian. Definisi ROC-AUC mengikuti Fawcett (2006).

{table(eval_tbl)}
Pada data uji independen, ambang {num(THR, 2)} menghasilkan recall {pct(H['recall'])}, **di bawah** target {pct(res['recall_target'])} yang tercapai pada validasi silang ({pct(O['recall'])}). Data uji hanya berisi {len(res['dataset']['holdout_fruits'])} buah, sehingga satu buah yang sulit ({anom_f.sort_values('rata_prob').iloc[0]['fruit_id']}, hanya {int(anom_f.sort_values('rata_prob').iloc[0]['scan_anomali'])} dari 8 sisi terdeteksi) sudah menggeser recall per pemindaian secara nyata.

![Confusion matrix]({figs['cm']})

*Gambar E. Matriks konfusi data uji independen ({len(hold)} pemindaian): {H['tn']} normal benar, {H['fp']} normal diputus anomali, {H['fn']} anomali lolos sebagai normal, dan {H['tp']} anomali tertangkap.*

![ROC]({figs['roc']})

*Gambar F. Kurva ROC validasi silang (AUC {num(O['roc_auc'])}) dan data uji independen (AUC {num(H['roc_auc'])}).*

### Putusan per buah (rata-rata 8 sisi)

Tabel C. Probabilitas anomali dirata-ratakan dari semua sisi satu buah, lalu dibandingkan dengan ambang yang sama.

{table(fruit_tbl)}
Dengan merata-ratakan semua sisi, **{fruit_correct} dari {len(per_fruit)} buah** terklasifikasi benar ({int((norm_f['putusan_rata_rata'] == 'normal').sum())}/{len(norm_f)} normal, {int((anom_f['putusan_rata_rata'] == 'anomali').sum())}/{len(anom_f)} anomali). Temuan analisis ini menunjukkan bahwa kerusakan internal tidak selalu berada pada jalur cahaya sisi yang dipindai. Alat conveyor memindai **satu kali per buah** pada sisi yang kebetulan menghadap sensor, sehingga angka yang berlaku di lapangan adalah angka per pemindaian pada Tabel B, bukan angka per buah ini.

![Per buah]({figs['per_buah']})

*Gambar G. Probabilitas anomali tiap sisi (titik) dan rata-ratanya (belah ketupat) untuk {len(per_fruit)} buah uji independen.*

## 6. Kepentingan kanal

![Kepentingan kanal]({figs['kanal']})

*Gambar H. Penurunan ROC-AUC ketika nilai satu kanal diacak (permutation importance, 30 ulangan, data uji independen). Batang merah menandai 730 dan 810 nm.*

Urutan kanal NIR menurut pengaruhnya; tiga teratas adalah {', '.join(f"{k} ({num(v)})" for k, v in zip(top['kanal'], top['penurunan_auc']))}.

## 7. Kinerja di server

- Pada alat conveyor, sensor PIR memicu lampu halogen dan satu pengukuran saat buah lewat. Hasil ditampilkan pada antrean web operator di ujung belt serta pada LCD dan buzzer alat.
- Model berjalan di server HP t530 (AMD GX-215JJ 2 inti 1,5 GHz, Python 3.14, scikit-learn 1.9.0). Waktu inferensi sekitar {INFER_MS} ms per pemindaian; satu siklus pemindaian melalui internet berlangsung sekitar 4 sampai 5 detik, terutama karena pemanasan lampu halogen selama 3 detik.
- Prediksi server identik dengan prediksi komputer pengembang untuk 20 pemindaian uji.
- Model demo saat ini dilatih dengan 80% buah agar data uji independen tetap bersih. Sebelum dipakai dengan alat fisik di mitra, model dilatih ulang dengan seluruh {res['dataset']['fruits']} buah (`python ml/evaluate_models.py --full`).

## 8. Keterbatasan

- Jumlah buah kecil ({res['dataset']['fruits']} buah; uji independen {len(res['dataset']['holdout_fruits'])} buah), sehingga selang ketidakpastian estimasi kinerja lebar.
- Label anomali menggabungkan beberapa penyebab kerusakan (larva lalat buah, busuk, memar), tidak terbatas pada infestasi tahap awal.
- Intensitas berupa nilai terkalibrasi sensor tanpa koreksi referensi putih dan gelap, sehingga peka terhadap perubahan lampu dan jarak.
- Seluruh data latih diambil dengan buah **diam** yang diputar manual 45°, sedangkan alat memindai buah yang **bergerak** di belt conveyor satu kali (dipicu sensor PIR), sehingga jarak, posisi, dan waktu pengukuran berbeda. Kinerja pada conveyor belum terbukti sampai data conveyor berlabel terkumpul dan model dilatih ulang (`ml/evaluate_models.py --data`).
- Uji lapangan dengan alat fisik di lokasi mitra belum dilakukan.
- Recall per pemindaian pada data uji independen ({pct(H['recall'])}) belum mencapai target {pct(res['recall_target'])}. Pilihan perbaikan untuk satu pemindaian per buah adalah menurunkan ambang (Tabel A2) dan menambah data conveyor.

## Daftar Pustaka

Breiman, L. 2001. Random forests. *Machine Learning*. 45(1):5-32. DOI: 10.1023/A:1010933404324.

Chicco, D. dan Jurman, G. 2020. The advantages of the Matthews correlation coefficient (MCC) over F1 score and accuracy in binary classification evaluation. *BMC Genomics*. 21(1):6. DOI: 10.1186/s12864-019-6413-7.

Cortes, C. dan Vapnik, V. 1995. Support-vector networks. *Machine Learning*. 20(3):273-297. DOI: 10.1007/BF00994018.

Fawcett, T. 2006. An introduction to ROC analysis. *Pattern Recognition Letters*. 27(8):861-874. DOI: 10.1016/j.patrec.2005.10.010.

Kapoor, S. dan Narayanan, A. 2023. Leakage and the reproducibility crisis in machine-learning-based science. *Patterns*. 4(9):100804. DOI: 10.1016/j.patter.2023.100804.

Provost, F. dan Fawcett, T. 2001. Robust classification for imprecise environments. *Machine Learning*. 42(3):203-231. DOI: 10.1023/A:1007601015854.

Roberts, D.R., Bahn, V., Ciuti, S., Boyce, M.S., Elith, J., Guillera-Arroita, G., Hauenstein, S., Lahoz-Monfort, J.J., Schröder, B., Thuiller, W., Warton, D.I., Wintle, B.A., Hartig, F. dan Dormann, C.F. 2017. Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*. 40(8):913-929. DOI: 10.1111/ecog.02881.

Varma, S. dan Simon, R. 2006. Bias in error estimation when using cross-validation for model selection. *BMC Bioinformatics*. 7:91. DOI: 10.1186/1471-2105-7-91.
"""
(DEST / "HASIL_ML.md").write_text(md, encoding="utf-8")


# ---------------- DOCX (dari Markdown yang sama) ----------------
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
      ("Diukur", "Sensor membaca cahaya tembus | 6 kanal NIR, sekali lewat"),
      ("Dikirim", "ESP32 mengirim lewat WiFi | mitra dan internet (HTTPS)"),
      ("Dinilai", f"Server mini PC menjalankan | model ML ({INFER_MS} ms)"),
      ("Disimpan", "Hasil masuk database | di server (backup harian)"),
      ("Ditampilkan", "Antrean web + LCD + bunyi | dengan nomor urut buah"),
      ("Dipilah", "Operator di ujung belt: | keranjang normal atau anomali")],
     "09_alur_satu_buah.png", "Perjalanan satu buah jambu di sistem BuahSafe")
flow([("Kumpulkan", "65 buah dipindai | 8 sisi = 518 scan"),
      ("Beri kunci jawaban", "Buah disimpan sampai | rusak tampak, lalu dibelah"),
      ("Sisihkan ujian", "13 buah disimpan untuk | ujian akhir, tidak dilihat"),
      ("Latih & bandingkan", "52 buah: LR, SVM, RF | dinilai bergiliran per buah"),
      ("Pilih", f"F1 tertinggi: | SVM {res['channel_set']} NIR"),
      ("Atur ambang", f"Ambang {num(THR, 2)} agar buah busuk | lebih jarang lolos"),
      ("Ujian akhir", "Diuji sekali pada | 13 buah tersimpan"),
      ("Pasang", "Model dipasang di server; | kelak dilatih ulang 65 buah")],
     "10_alur_melatih_model.png", "Bagaimana model BuahSafe dilatih dan diuji")

penjelasan = DEST / "PENJELASAN_ALUR_BUAHSAFE.md"
if penjelasan.exists():
    md_to_docx(penjelasan.read_text(encoding="utf-8"), DEST, DEST / "PENJELASAN_ALUR_BUAHSAFE.docx")
print(f"Bahan laporan ditulis ke {DEST} ({len(figs)} gambar, xlsx, md, docx)")
