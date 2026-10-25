"""BuahSafe Spectral Machine Learning Predictor Service.

Loads the trained model (channels + anomaly threshold from the artifact) and performs real-time classification
of AS7265x spectral scans into 'NORMAL' or 'ANOMALI' with confidence estimation.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import joblib
import numpy as np

logger = logging.getLogger("buahsafe.predictor")

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "buahsafe_model.joblib"  # dibuat oleh ml/evaluate_models.py

# 6 kanal NIR & red-edge paling diskriminatif hasil seleksi fitur Monev 3
CH6 = ["nm610", "nm680", "nm730", "nm760", "nm810", "nm860"]
ALL_18_CHANNELS = [
    "nm410", "nm435", "nm460", "nm485", "nm510", "nm535",
    "nm560", "nm585", "nm610", "nm645", "nm680", "nm705",
    "nm730", "nm760", "nm810", "nm860", "nm900", "nm940"
]

_ARTIFACT: dict[str, Any] | None = None


def load_model() -> dict[str, Any] | None:
    """Muat model dari disk jika belum dimuat."""
    global _ARTIFACT
    if _ARTIFACT is not None:
        return _ARTIFACT

    if not MODEL_PATH.exists():
        logger.warning("File model ML tidak ditemukan di %s", MODEL_PATH)
        return None

    try:
        _ARTIFACT = joblib.load(MODEL_PATH)
        logger.info(
            "Model BuahSafe SVM berhasil dimuat (versi %s, Akurasi: %.1f%%)",
            _ARTIFACT.get("version", "1.0.0"),
            _ARTIFACT.get("metrics", {}).get("accuracy", 0.0) * 100,
        )
        return _ARTIFACT
    except Exception as exc:
        logger.exception("Gagal memuat model ML: %s", exc)
        return None


def model_channels(artifact: dict[str, Any] | None = None) -> list[str]:
    """Kanal yang dibutuhkan model aktif (artefak lama tanpa 'channels' = 6 kanal)."""
    artifact = artifact if artifact is not None else load_model()
    return list((artifact or {}).get("channels") or CH6)


def extract_features(data: Mapping[str, Any] | Sequence[float], channels: Sequence[str] = CH6) -> list[float]:
    """Ambil nilai kanal yang diminta dari dict kanal ('nm610', ...) atau list 18 nilai."""
    if isinstance(data, (list, tuple)):
        if len(data) == 18:
            data = dict(zip(ALL_18_CHANNELS, data))
        elif len(data) == len(channels):
            data = dict(zip(channels, data))
        else:
            raise ValueError(f"Jumlah kanal tidak sesuai: diterima {len(data)}, diharapkan {len(channels)} atau 18")
    if not isinstance(data, Mapping):
        raise TypeError(f"Tipe data spektral tidak didukung: {type(data).__name__}")

    values: list[float] = []
    for ch in channels:
        if ch not in data:
            raise ValueError(f"Kanal spektral wajib '{ch}' tidak ditemukan dalam data")
        val = float(data[ch])
        if np.isnan(val) or np.isinf(val):
            raise ValueError(f"Nilai kanal '{ch}' tidak valid (NaN/Inf): {val}")
        values.append(val)
    return values


def predict(spectral_data: Mapping[str, Any] | Sequence[float]) -> dict[str, Any]:
    """Lakukan inferensi klasifikasi spektral buah.

    Kanal dan ambang probabilitas anomali dibaca dari artefak model
    (ml/evaluate_models.py). Ambang < 0,5 sengaja dipilih agar lebih sedikit
    buah busuk yang lolos ke keranjang hijau.

    Mengembalikan:
      - result: 'NORMAL' atau 'ANOMALI'
      - confidence: probabilitas kelas yang diputuskan (0 - 100%)
      - probabilities: probabilitas normal vs anomali
      - threshold: ambang anomali yang dipakai
      - key_features: nilai kanal yang dievaluasi
    """
    artifact = load_model()
    if artifact is None or "pipeline" not in artifact:
        # Tanpa model terlatih tidak ada putusan: heuristik tebakan di lantai sortasi
        # akan mengirim buah ke keranjang yang salah tanpa disadari operator.
        raise RuntimeError(f"Model ML tidak tersedia atau rusak: {MODEL_PATH.name}")

    channels = model_channels(artifact)
    features = extract_features(spectral_data, channels)
    threshold = float(artifact.get("threshold", 0.5))
    prob = artifact["pipeline"].predict_proba(np.array([features]))[0]
    p_norm, p_anom = float(prob[0]), float(prob[1])
    is_anomali = p_anom >= threshold

    return {
        "result": "ANOMALI" if is_anomali else "NORMAL",
        "confidence": round((p_anom if is_anomali else p_norm) * 100.0, 1),
        "probabilities": {
            "normal": round(p_norm * 100.0, 1),
            "anomali": round(p_anom * 100.0, 1),
        },
        "threshold": threshold,
        "key_features": {ch: round(val, 4) for ch, val in zip(channels, features)},
        "model_status": artifact.get("model_name", "svm_rbf") + " " + artifact.get("channel_set", "6 kanal"),
        "model_metrics": artifact.get("metrics", {}),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Menguji modul predictor...")
    res = predict([1.5] * 18)
    print("Hasil Prediksi Uji:", res)
