"""Evaluasi adil model BuahSafe dan ekspor model produksi.

Langkah (semua pemisahan per BUAH, bukan per scan, supaya 8 rotasi satu buah
tidak bocor ke data latih dan data uji sekaligus):
  1. Sisihkan ~20% buah sebagai HOLDOUT (stratifikasi kelas). Tidak disentuh
     sampai langkah 4. Daftarnya dipakai juga oleh esp32_simulator.py.
  2. Nested CV pada 80% sisanya: luar 5-fold untuk menilai, dalam 4-fold
     GridSearchCV (scoring F1) untuk tuning. Kandidat: LR, SVM-RBF, RF x
     (6 kanal, 18 kanal).
  3. Pilih kandidat 6 kanal NIR (610-860 nm, setara sensor AS7263 dan chip
     AS72651) dengan F1 nested tertinggi; 18 kanal hanya pembanding. Kanal
     visible 485 nm bernilai 0 pada sebagian besar scan. Ambang probabilitas anomali
     dipilih dari prediksi out-of-fold: ambang TERTINGGI yang masih memberi
     recall anomali >= RECALL_TARGET (buah busuk yang lolos lebih mahal
     daripada buah sehat yang diperiksa ulang).
  4. Tuning ulang pada seluruh 80%, latih, lalu uji SEKALI di holdout.
  5. Simpan models/buahsafe_model.joblib (+ ringkasan di ml/output/).

Pemakaian:
  python ml/evaluate_models.py          # model demo, dilatih 80% data
  python ml/evaluate_models.py --full   # pakai ulang hasil seleksi, latih 100% data
  python ml/evaluate_models.py --data conveyor.csv   # tambah scan conveyor berlabel
    (conveyor.csv = unduhan /export.csv; hanya baris berlabel normal/anomali yang dipakai)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "output" / "finalised" / "buahsafe_dataset_gabungan_final.csv"
OUT = ROOT / "ml" / "output"
HOLDOUT_FILE = ROOT / "ml" / "holdout_fruits.json"
MODEL_OUT = ROOT / "models" / "buahsafe_model.joblib"

SEED = 42
RECALL_TARGET = 0.80
CH18 = ["nm410", "nm435", "nm460", "nm485", "nm510", "nm535", "nm560", "nm585", "nm610",
        "nm645", "nm680", "nm705", "nm730", "nm760", "nm810", "nm860", "nm900", "nm940"]
CH6 = ["nm610", "nm680", "nm730", "nm760", "nm810", "nm860"]
CHANNEL_SETS = {"6 kanal": CH6, "18 kanal": CH18}
MAIN_SET = "6 kanal"  # desain penelitian: hanya kanal NIR; 18 kanal sebagai pembanding


def load_data(extra: list[str]) -> pd.DataFrame:
    """Dataset final + CSV tambahan. Baris tanpa label atau tanpa 18 kanal dibuang."""
    frames = [pd.read_csv(DATA)] + [pd.read_csv(path) for path in extra]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["label"].isin(["normal", "anomali"])].dropna(subset=CH18)
    return df.drop_duplicates(subset=["fruit_id", "timestamp"]).reset_index(drop=True)


def candidates() -> dict[str, tuple[Pipeline, dict]]:
    return {
        "Logistic Regression": (
            Pipeline([("scale", StandardScaler()),
                      ("clf", LogisticRegression(max_iter=5000, random_state=SEED))]),
            {"clf__C": [0.01, 0.1, 1, 10, 100]},
        ),
        "SVM (RBF)": (
            Pipeline([("scale", StandardScaler()),
                      ("clf", SVC(kernel="rbf", probability=True, random_state=SEED))]),
            {"clf__C": [0.1, 1, 10, 100], "clf__gamma": ["scale", 0.01, 0.1, 1]},
        ),
        "Random Forest": (
            Pipeline([("clf", RandomForestClassifier(random_state=SEED, n_jobs=-1))]),
            {"clf__n_estimators": [200, 400], "clf__max_depth": [None, 5, 10],
             "clf__min_samples_leaf": [1, 2, 4]},
        ),
    }


def metrics(y: np.ndarray, prob: np.ndarray, threshold: float) -> dict[str, float]:
    pred = (prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "accuracy": accuracy_score(y, pred),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "specificity": float(tn / (tn + fp)) if tn + fp else 0.0,
        "f1": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, prob),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def pick_threshold(y: np.ndarray, prob: np.ndarray) -> float:
    """Ambang tertinggi dengan recall anomali >= RECALL_TARGET (dari prediksi out-of-fold)."""
    ok = [t for t in np.round(np.arange(0.05, 0.951, 0.01), 2)
          if recall_score(y, (prob >= t).astype(int)) >= RECALL_TARGET]
    return float(max(ok)) if ok else 0.5


def tune(name: str, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> GridSearchCV:
    estimator, grid = candidates()[name]
    search = GridSearchCV(estimator, grid, scoring="f1", n_jobs=-1,
                          cv=StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=SEED))
    return search.fit(X, y, groups=groups)


def split_holdout(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    fruits = df.groupby("fruit_id")["label"].first()
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    _, test_idx = next(splitter.split(fruits.index, fruits.values, groups=fruits.index))
    holdout = sorted(fruits.index[test_idx])
    mask = df["fruit_id"].isin(holdout)
    return df[~mask].reset_index(drop=True), df[mask].reset_index(drop=True), holdout


def run_selection(dev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Nested CV semua kandidat. Kembalikan metrik per fold, ringkasan, dan prediksi out-of-fold."""
    y = (dev["label"] == "anomali").astype(int).to_numpy()
    groups = dev["fruit_id"].to_numpy()
    outer = list(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED).split(dev, y, groups))
    fold_rows, oof_rows = [], []
    for set_name, channels in CHANNEL_SETS.items():
        X = dev[channels].to_numpy()
        for model_name in candidates():
            oof = np.zeros(len(y))
            for fold, (tr, te) in enumerate(outer, 1):
                search = tune(model_name, X[tr], y[tr], groups[tr])
                prob = search.predict_proba(X[te])[:, 1]
                oof[te] = prob
                fold_rows.append({"model": model_name, "channels": set_name, "fold": fold,
                                  "best_params": json.dumps(search.best_params_),
                                  **metrics(y[te], prob, 0.5)})
            oof_rows.append(pd.DataFrame({"model": model_name, "channels": set_name,
                                          "fruit_id": groups, "y": y, "prob": oof}))
            print(f"  {model_name:<20} {set_name:<9} F1 fold-mean "
                  f"{np.mean([r['f1'] for r in fold_rows if r['model'] == model_name and r['channels'] == set_name]):.3f}")
    folds = pd.DataFrame(fold_rows)
    metric_cols = ["accuracy", "precision", "recall", "specificity", "f1", "roc_auc"]
    summary = folds.groupby(["model", "channels"])[metric_cols].agg(["mean", "std"])
    summary.columns = [f"{m}_{s}" for m, s in summary.columns]
    summary = summary.reset_index().sort_values("f1_mean", ascending=False)
    return folds, summary, pd.concat(oof_rows, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="latih model terpilih dengan 100%% data")
    parser.add_argument("--data", action="append", default=[], help="CSV tambahan (mis. scan conveyor berlabel)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_data(args.data)

    if args.full:
        meta = joblib.load(MODEL_OUT)
        channels, name = meta["channels"], meta["model_name"]
        y = (df["label"] == "anomali").astype(int).to_numpy()
        search = tune(name, df[channels].to_numpy(), y, df["fruit_id"].to_numpy())
        meta.update(pipeline=search.best_estimator_, params=search.best_params_,
                    trained_on=f"100% data ({df['fruit_id'].nunique()} buah, {len(df)} scan)",
                    created=datetime.now().isoformat(timespec="seconds"))
        joblib.dump(meta, MODEL_OUT)
        print(f"Model {name} ({meta['channel_set']}) dilatih ulang dengan 100% data -> {MODEL_OUT}")
        return

    dev, hold, holdout_fruits = split_holdout(df)
    HOLDOUT_FILE.write_text(json.dumps({
        "seed": SEED, "fruits": holdout_fruits,
        "note": "Buah ini tidak dipakai melatih/menyeleksi model demo; hanya untuk uji akhir dan esp32_simulator.py",
    }, indent=2), encoding="utf-8")
    print(f"Dev: {dev['fruit_id'].nunique()} buah / {len(dev)} scan | "
          f"Holdout: {len(holdout_fruits)} buah / {len(hold)} scan "
          f"({hold.groupby('fruit_id')['label'].first().value_counts().to_dict()})")

    print("Nested CV (luar 5-fold, dalam 4-fold, per buah):")
    folds, summary, oof = run_selection(dev)
    best = summary[summary["channels"] == MAIN_SET].iloc[0]
    name, set_name = best["model"], best["channels"]
    channels = CHANNEL_SETS[set_name]
    best_oof = oof[(oof["model"] == name) & (oof["channels"] == set_name)]
    threshold = pick_threshold(best_oof["y"].to_numpy(), best_oof["prob"].to_numpy())
    oof_at_threshold = metrics(best_oof["y"].to_numpy(), best_oof["prob"].to_numpy(), threshold)
    print(f"Terpilih: {name} {set_name} (F1 nested {best['f1_mean']:.3f}) | ambang anomali {threshold:.2f}")

    y_dev = (dev["label"] == "anomali").astype(int).to_numpy()
    search = tune(name, dev[channels].to_numpy(), y_dev, dev["fruit_id"].to_numpy())
    model = search.best_estimator_
    y_hold = (hold["label"] == "anomali").astype(int).to_numpy()
    prob_hold = model.predict_proba(hold[channels].to_numpy())[:, 1]
    holdout = {"threshold": metrics(y_hold, prob_hold, threshold), "default_0.5": metrics(y_hold, prob_hold, 0.5)}
    print(f"Holdout @ambang {threshold:.2f}: " + ", ".join(f"{k} {v:.3f}" for k, v in holdout["threshold"].items() if isinstance(v, float)))

    folds.to_csv(OUT / "nested_cv_per_fold.csv", index=False)
    summary.to_csv(OUT / "nested_cv_summary.csv", index=False)
    oof.to_csv(OUT / "nested_cv_oof_predictions.csv", index=False)
    pd.DataFrame({"fruit_id": hold["fruit_id"], "rotasi": hold.get("rotasi_buah"), "label": hold["label"],
                  "prob_anomali": prob_hold.round(4),
                  "prediksi": np.where(prob_hold >= threshold, "anomali", "normal")}).to_csv(
        OUT / "holdout_predictions.csv", index=False)

    result = {
        "model_name": name, "channel_set": set_name, "channels": channels, "threshold": threshold,
        "recall_target": RECALL_TARGET, "params": search.best_params_,
        "nested_cv_mean": {k: float(best[f"{k}_mean"]) for k in ["accuracy", "precision", "recall", "specificity", "f1", "roc_auc"]},
        "nested_cv_oof_at_threshold": oof_at_threshold, "holdout": holdout,
        "dataset": {"scans": len(df), "fruits": int(df["fruit_id"].nunique()),
                    "dev_fruits": int(dev["fruit_id"].nunique()), "holdout_fruits": holdout_fruits},
    }
    (OUT / "selection_result.json").write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    joblib.dump({
        "pipeline": model, "version": "2.0.0", "sklearn_version": sklearn.__version__,
        "trained_on": f"80% data ({dev['fruit_id'].nunique()} buah, {len(dev)} scan); holdout di ml/holdout_fruits.json",
        "created": datetime.now().isoformat(timespec="seconds"),
        # metrics.accuracy dibaca predictor.load_model() untuk log
        "metrics": {**result["holdout"]["threshold"], "source": "holdout"},
        **{k: result[k] for k in ["model_name", "channel_set", "channels", "threshold", "params",
                                  "nested_cv_mean", "holdout"]},
    }, MODEL_OUT)
    print(f"Model disimpan: {MODEL_OUT}")


if __name__ == "__main__":
    sys.exit(main())
