"""Compare classifier performance between the 29082026 and 08092026 (label-cleaned) gabungan datasets.

Same model (RandomForest, fixed random_state), same features (18 spectral channels),
same evaluation (5-fold GroupKFold grouped by fruit_id so scans of one fruit never
span train/test — see README.md "Catatan pengambilan dataset").
"""
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
FIXED = os.path.join(BASE, "..", "fixed")
OUT_DIR = os.path.join(BASE, "model_comparison_output")
os.makedirs(OUT_DIR, exist_ok=True)

FEATURES = ["nm410", "nm435", "nm460", "nm485", "nm510", "nm535", "nm560", "nm585",
            "nm610", "nm645", "nm680", "nm705", "nm730", "nm760", "nm810", "nm860", "nm900", "nm940"]

DATASETS = {
    "29082026": os.path.join(FIXED, "buahsafe_dataset_gabungan_29082026.xlsx"),
    "08092026_clean": os.path.join(FIXED, "buahsafe_dataset_gabungan_08092026_clean.xlsx"),
}


def evaluate(path, n_splits=5, seed=42):
    df = pd.read_excel(path)
    X = df[FEATURES].values
    y = (df["label"] == "anomali").astype(int).values
    groups = df["fruit_id"].values

    gkf = GroupKFold(n_splits=n_splits)
    rows = []
    for fold, (tr, te) in enumerate(gkf.split(X, y, groups), 1):
        clf = RandomForestClassifier(n_estimators=200, random_state=seed)
        clf.fit(X[tr], y[tr])
        pred = clf.predict(X[te])
        proba = clf.predict_proba(X[te])[:, 1]
        rows.append({
            "fold": fold,
            "n_train": len(tr),
            "n_test": len(te),
            "accuracy": accuracy_score(y[te], pred),
            "precision": precision_score(y[te], pred),
            "recall": recall_score(y[te], pred),
            "f1": f1_score(y[te], pred),
            "roc_auc": roc_auc_score(y[te], proba),
        })
    return df, pd.DataFrame(rows)


def main():
    summary = []
    per_fold = {}
    for name, path in DATASETS.items():
        df, folds = evaluate(path)
        per_fold[name] = folds
        row = {"dataset": name, "n_rows": len(df), "n_fruits": df["fruit_id"].nunique()}
        for metric in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
            row[f"{metric}_mean"] = folds[metric].mean()
            row[f"{metric}_std"] = folds[metric].std()
        summary.append(row)

    df_summary = pd.DataFrame(summary)
    df_summary.to_csv(os.path.join(OUT_DIR, "model_comparison_summary.csv"), index=False)

    all_folds = pd.concat(
        [f.assign(dataset=name) for name, f in per_fold.items()], ignore_index=True
    )
    all_folds.to_csv(os.path.join(OUT_DIR, "model_comparison_per_fold.csv"), index=False)

    print(df_summary.to_string(index=False))

    # Bar chart: mean +/- std per metric per dataset
    metrics = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    x = np.arange(len(metrics))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = {"29082026": "#7f7f7f", "08092026_clean": "#2ca02c"}
    for i, name in enumerate(DATASETS):
        row = df_summary[df_summary["dataset"] == name].iloc[0]
        means = [row[f"{m}_mean"] for m in metrics]
        stds = [row[f"{m}_std"] for m in metrics]
        ax.bar(x + (i - 0.5) * width, means, width, yerr=stds, capsize=4,
               label=f"{name} (n={row['n_rows']}, fruits={row['n_fruits']})", color=colors[name])
    ax.set_xticks(x)
    ax.set_xticklabels([m.upper() for m in metrics])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Skor (5-fold GroupKFold by fruit_id)")
    ax.set_title("Perbandingan Performa Model: Dataset 29082026 vs 08092026 (label bersih)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plot_path = os.path.join(OUT_DIR, "model_comparison_plot.png")
    plt.savefig(plot_path, dpi=300)
    plt.close()
    print(f"\n[SUKSES] Disimpan di: {OUT_DIR}")


def _selfcheck():
    df, folds = evaluate(DATASETS["29082026"], n_splits=3)
    assert len(folds) == 3
    assert folds["accuracy"].between(0, 1).all()


if __name__ == "__main__":
    _selfcheck()
    main()
