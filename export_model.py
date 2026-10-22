"""Export production machine learning model for BuahSafe.

Trains an optimal SVM (RBF) classifier on the 6 key Visible-NIR channels
(610, 680, 730, 760, 810, 860 nm) and serializes the complete pipeline
with metadata to a .joblib file for instant server inference.
"""
import os
import sys
from datetime import datetime
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score, f1_score
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "output", "finalised", "buahsafe_dataset_gabungan_final.csv")
if not os.path.exists(DATA_PATH):
    DATA_PATH = os.path.join(ROOT, "output", "arsip", "buahsafe_dataset_gabungan_final.csv")

MODEL_DIR = os.path.join(ROOT, "models")
os.makedirs(MODEL_DIR, exist_ok=True)
MODEL_OUT = os.path.join(MODEL_DIR, "buahsafe_model_svm_6ch.joblib")

CH6 = ["nm610", "nm680", "nm730", "nm760", "nm810", "nm860"]
CLASSES = ["normal", "anomali"]

def train_and_export():
    print(f"Memuat dataset dari {DATA_PATH}...")
    df = pd.read_csv(DATA_PATH)
    
    # Validasi kanal
    for col in CH6:
        if col not in df.columns:
            raise ValueError(f"Kanal {col} tidak ditemukan dalam dataset")
            
    X = df[CH6].values
    y = (df["label"] == "anomali").astype(int).values
    groups = df["fruit_id"].values
    
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("svm", SVC(C=100.0, kernel="rbf", gamma="scale", probability=True, random_state=42))
    ])
    
    # Evaluasi GroupKFold (objek-aware)
    gkf = GroupKFold(n_splits=5)
    y_pred = cross_val_predict(pipeline, X, y, groups=groups, cv=gkf, method="predict")
    y_prob = cross_val_predict(pipeline, X, y, groups=groups, cv=gkf, method="predict_proba")[:, 1]
    
    acc = accuracy_score(y, y_pred)
    f1 = f1_score(y, y_pred)
    auc = roc_auc_score(y, y_prob)
    
    print(f"Hasil Evaluasi GroupKFold (5-fold):")
    print(f"  - Akurasi : {acc * 100:.2f}%")
    print(f"  - F1-Score: {f1 * 100:.2f}%")
    print(f"  - ROC-AUC : {auc * 100:.2f}%")
    
    # Fit pada seluruh data untuk deployment produksi
    pipeline.fit(X, y)
    
    artifact = {
        "pipeline": pipeline,
        "feature_names": CH6,
        "wavelengths": [int(c[2:]) for c in CH6],
        "classes": CLASSES,
        "metrics": {
            "accuracy": float(acc),
            "f1": float(f1),
            "roc_auc": float(auc)
        },
        "trained_at": datetime.now().isoformat(),
        "training_samples": len(df),
        "unique_objects": int(df["fruit_id"].nunique()),
        "version": "1.0.0"
    }
    
    joblib.dump(artifact, MODEL_OUT)
    print(f"Model berhasil diekspor ke: {MODEL_OUT}")
    print(f"Ukuran file: {os.path.getsize(MODEL_OUT) / 1024:.1f} KB")

if __name__ == "__main__":
    train_and_export()
