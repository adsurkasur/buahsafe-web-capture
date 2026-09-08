"""Compare Logistic Regression, Random Forest, and SVM on the AS7263 main channels
(610/680/730/760/810/860 nm) — the sensor the research is focused on.

Dataset: latest cleaned gabungan (08092026). Evaluation: 5-fold GroupKFold by
fruit_id (no fruit spans train/test — see README.md "Catatan pengambilan dataset").
"""
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

BASE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(BASE, "..", "fixed", "buahsafe_dataset_gabungan_08092026_clean.xlsx")
OUT_DIR = os.path.join(BASE, "model_comparison_output")
os.makedirs(OUT_DIR, exist_ok=True)

MAIN_CHANNELS = ["nm610", "nm680", "nm730", "nm760", "nm810", "nm860"]
SEED = 42

MODELS = {
    "LogisticRegression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=SEED)),
    "RandomForest": RandomForestClassifier(n_estimators=200, random_state=SEED),
    "SVM": make_pipeline(StandardScaler(), SVC(kernel="rbf", probability=True, random_state=SEED)),
}


def evaluate(df, model_name, n_splits=5):
    X = df[MAIN_CHANNELS].values
    y = (df["label"] == "anomali").astype(int).values
    groups = df["fruit_id"].values

    gkf = GroupKFold(n_splits=n_splits)
    rows = []
    for fold, (tr, te) in enumerate(gkf.split(X, y, groups), 1):
        model = MODELS[model_name]
        model.fit(X[tr], y[tr])
        pred = model.predict(X[te])
        proba = model.predict_proba(X[te])[:, 1]
        rows.append({
            "fold": fold,
            "accuracy": accuracy_score(y[te], pred),
            "precision": precision_score(y[te], pred, zero_division=0),
            "recall": recall_score(y[te], pred, zero_division=0),
            "f1": f1_score(y[te], pred, zero_division=0),
            "roc_auc": roc_auc_score(y[te], proba),
        })
    return pd.DataFrame(rows)


def main():
    df = pd.read_excel(DATASET)
    print(f"[DATA] {len(df)} baris, {df['fruit_id'].nunique()} buah, kanal: {MAIN_CHANNELS}")

    summary = []
    per_fold = []
    for name in MODELS:
        folds = evaluate(df, name)
        per_fold.append(folds.assign(model=name))
        row = {"model": name}
        for metric in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
            row[f"{metric}_mean"] = folds[metric].mean()
            row[f"{metric}_std"] = folds[metric].std()
        summary.append(row)

    df_summary = pd.DataFrame(summary)
    df_summary.to_csv(os.path.join(OUT_DIR, "model_algo_comparison_summary.csv"), index=False)
    pd.concat(per_fold, ignore_index=True).to_csv(
        os.path.join(OUT_DIR, "model_algo_comparison_per_fold.csv"), index=False
    )
    print(df_summary.to_string(index=False))

    metrics = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    x = np.arange(len(metrics))
    width = 0.25
    colors = {"LogisticRegression": "#1f77b4", "RandomForest": "#2ca02c", "SVM": "#d62728"}
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, name in enumerate(MODELS):
        row = df_summary[df_summary["model"] == name].iloc[0]
        means = [row[f"{m}_mean"] for m in metrics]
        stds = [row[f"{m}_std"] for m in metrics]
        ax.bar(x + (i - 1) * width, means, width, yerr=stds, capsize=4, label=name, color=colors[name])
    ax.set_xticks(x)
    ax.set_xticklabels([m.upper() for m in metrics])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Skor (5-fold GroupKFold by fruit_id)")
    ax.set_title(f"Perbandingan Model — 6 Kanal Utama AS7263 ({len(df)} baris, {df['fruit_id'].nunique()} buah)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plot_path = os.path.join(OUT_DIR, "model_algo_comparison_plot.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"\n[SUKSES] Disimpan di: {OUT_DIR}")


def _selfcheck():
    df = pd.read_excel(DATASET)
    subset = pd.concat([df[df["label"] == "anomali"].head(60), df[df["label"] == "normal"].head(60)])
    folds = evaluate(subset, "LogisticRegression", n_splits=3)
    assert folds["accuracy"].between(0, 1).all()


if __name__ == "__main__":
    _selfcheck()
    main()
