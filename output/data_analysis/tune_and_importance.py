"""Hyperparameter tuning + feature importance breakdown for LR/RF/SVM on the
BuahSafe internal dev/test dataset (AMAN/BOSOK, NOT the jambu kristal primary
research data). 6 main AS7263 channels only. Grouped by fruit_id throughout.
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
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.inspection import permutation_importance

BASE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(BASE, "..", "fixed", "buahsafe_dataset_gabungan_08092026_clean.xlsx")
OUT_DIR = os.path.join(BASE, "model_comparison_output")
os.makedirs(OUT_DIR, exist_ok=True)

MAIN_CHANNELS = ["nm610", "nm680", "nm730", "nm760", "nm810", "nm860"]
SEED = 42
N_SPLITS = 5

PARAM_GRIDS = {
    "LogisticRegression": (
        make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=SEED)),
        {"logisticregression__C": [0.01, 0.1, 1, 10, 100]},
    ),
    "RandomForest": (
        RandomForestClassifier(random_state=SEED),
        {
            "n_estimators": [100, 200, 400],
            "max_depth": [None, 5, 10, 20],
            "min_samples_leaf": [1, 2, 4],
        },
    ),
    "SVM": (
        make_pipeline(StandardScaler(), SVC(kernel="rbf", probability=True, random_state=SEED)),
        {"svc__C": [0.1, 1, 10, 100], "svc__gamma": ["scale", 0.1, 0.01, 1]},
    ),
}


def load_xy(df):
    X = df[MAIN_CHANNELS].values
    y = (df["label"] == "anomali").astype(int).values
    groups = df["fruit_id"].values
    return X, y, groups


def tune(df):
    X, y, groups = load_xy(df)
    best = {}
    for name, (estimator, grid) in PARAM_GRIDS.items():
        search = GridSearchCV(estimator, grid, scoring="f1", cv=GroupKFold(N_SPLITS), n_jobs=-1)
        search.fit(X, y, groups=groups)
        best[name] = search.best_estimator_
        print(f"[TUNE] {name}: best_params={search.best_params_} best_cv_f1={search.best_score_:.4f}")
    return best


def evaluate(df, build_model_fn):
    X, y, groups = load_xy(df)
    gkf = GroupKFold(N_SPLITS)
    rows = []
    for fold, (tr, te) in enumerate(gkf.split(X, y, groups), 1):
        model = build_model_fn()
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
    print(f"[DATA] {len(df)} baris, {df['fruit_id'].nunique()} buah (dev/test dataset, bukan data primer)")

    print("\n[STEP 1] Hyperparameter tuning (GridSearchCV, scoring=f1, GroupKFold 5-fold)...")
    best_models = tune(df)

    print("\n[STEP 2] Evaluasi model ter-tuning (5-fold GroupKFold, refit per fold)...")
    from sklearn.base import clone
    summary = []
    per_fold = []
    for name, fitted in best_models.items():
        build_fn = lambda est=fitted: clone(est)
        folds = evaluate(df, build_fn)
        per_fold.append(folds.assign(model=name))
        row = {"model": name}
        for metric in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
            row[f"{metric}_mean"] = folds[metric].mean()
            row[f"{metric}_std"] = folds[metric].std()
        summary.append(row)

    df_summary = pd.DataFrame(summary)
    df_summary.to_csv(os.path.join(OUT_DIR, "tuned_model_summary.csv"), index=False)
    pd.concat(per_fold, ignore_index=True).to_csv(os.path.join(OUT_DIR, "tuned_model_per_fold.csv"), index=False)
    print(df_summary.to_string(index=False))

    print("\n[STEP 3] Feature importance (permutation importance, scoring=f1, n_repeats=30)...")
    X, y, groups = load_xy(df)
    imp_rows = []
    for name, model in best_models.items():
        model.fit(X, y)
        result = permutation_importance(model, X, y, scoring="f1", n_repeats=30, random_state=SEED, n_jobs=-1)
        for ch, mean_imp, std_imp in zip(MAIN_CHANNELS, result.importances_mean, result.importances_std):
            imp_rows.append({"model": name, "channel": ch, "importance_mean": mean_imp, "importance_std": std_imp})

    df_imp = pd.DataFrame(imp_rows)
    df_imp.to_csv(os.path.join(OUT_DIR, "feature_importance.csv"), index=False)
    print(df_imp.pivot(index="channel", columns="model", values="importance_mean").to_string())

    # Plot: tuned model comparison
    metrics = ["accuracy", "precision", "recall", "f1", "roc_auc"]
    x = np.arange(len(metrics))
    width = 0.25
    colors = {"LogisticRegression": "#1f77b4", "RandomForest": "#2ca02c", "SVM": "#d62728"}
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, name in enumerate(best_models):
        row = df_summary[df_summary["model"] == name].iloc[0]
        means = [row[f"{m}_mean"] for m in metrics]
        stds = [row[f"{m}_std"] for m in metrics]
        ax.bar(x + (i - 1) * width, means, width, yerr=stds, capsize=4, label=name, color=colors[name])
    ax.set_xticks(x)
    ax.set_xticklabels([m.upper() for m in metrics])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Skor (5-fold GroupKFold by fruit_id)")
    ax.set_title("Model Ter-tuning — 6 Kanal Utama (data uji coba internal BuahSafe)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "tuned_model_plot.png"), dpi=300)
    plt.close()

    # Plot: feature importance
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(MAIN_CHANNELS))
    for i, name in enumerate(best_models):
        sub = df_imp[df_imp["model"] == name].set_index("channel").loc[MAIN_CHANNELS]
        ax.bar(x + (i - 1) * width, sub["importance_mean"], width, yerr=sub["importance_std"],
               capsize=4, label=name, color=colors[name])
    ax.set_xticks(x)
    ax.set_xticklabels(MAIN_CHANNELS)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Permutation importance (delta F1)")
    ax.set_title("Feature Importance per Kanal (permutation importance, n_repeats=30)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "feature_importance_plot.png"), dpi=300)
    plt.close()

    print(f"\n[SUKSES] Disimpan di: {OUT_DIR}")


def _selfcheck():
    df = pd.read_excel(DATASET)
    subset = pd.concat([df[df["label"] == "anomali"].head(60), df[df["label"] == "normal"].head(60)])
    X, y, groups = load_xy(subset)
    assert len(np.unique(y)) == 2
    folds = evaluate(subset, lambda: RandomForestClassifier(n_estimators=50, random_state=SEED))
    assert folds["accuracy"].between(0, 1).all()


if __name__ == "__main__":
    _selfcheck()
    main()
