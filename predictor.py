"""BuahSafe Spectral Machine Learning Predictor Service.

Loads the trained 6-channel SVM RBF model and performs real-time classification
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
MODEL_PATH = ROOT / "models" / "buahsafe_model_svm_6ch.joblib"

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


def extract_features(data: Mapping[str, Any] | Sequence[float]) -> list[float]:
    """Ekstrak nilai 6 kanal spektral dari dict kanal atau list angka."""
    if isinstance(data, Mapping):
        # Dict dengan key seperti 'nm610' dsb.
        values: list[float] = []
        for ch in CH6:
            if ch not in data:
                raise ValueError(f"Kanal spektral wajib '{ch}' tidak ditemukan dalam data")
            val = float(data[ch])
            if np.isnan(val) or np.isinf(val):
                raise ValueError(f"Nilai kanal '{ch}' tidak valid (NaN/Inf): {val}")
            values.append(val)
        return values

    if isinstance(data, (list, tuple)):
        # Jika panjang 18 kanal penuh, ambil indeks kanal 6
        if len(data) == 18:
            idx_map = {name: i for i, name in enumerate(ALL_18_CHANNELS)}
            return [float(data[idx_map[ch]]) for ch in CH6]
        # Jika tepat 6 kanal
        if len(data) == 6:
            return [float(v) for v in data]
        raise ValueError(f"Jumlah kanal tidak sesuai: diterima {len(data)}, diharapkan 6 atau 18")

    raise TypeError(f"Tipe data spektral tidak didukung: {type(data).__name__}")


def predict(spectral_data: Mapping[str, Any] | Sequence[float]) -> dict[str, Any]:
    """Lakukan inferensi klasifikasi spektral buah.

    Mengembalikan:
      - result: 'NORMAL' atau 'ANOMALI'
      - confidence: tingkat keyakinan (0 - 100%)
      - probabilities: probabilitas normal vs anomali
      - key_features: nilai 6 kanal yang dievaluasi
    """
    x6 = extract_features(spectral_data)
    artifact = load_model()

    if artifact is None or "pipeline" not in artifact:
        # Tanpa model terlatih tidak ada putusan: heuristik tebakan di lantai sortasi
        # akan mengirim buah ke keranjang yang salah tanpa disadari operator.
        raise RuntimeError(f"Model ML tidak tersedia atau rusak: {MODEL_PATH.name}")

    pipeline = artifact["pipeline"]
    X = np.array([x6])

    # Prediksi probabilitas
    prob = pipeline.predict_proba(X)[0]
    p_norm = float(prob[0])
    p_anom = float(prob[1])

    is_anomali = p_anom >= 0.5
    result = "ANOMALI" if is_anomali else "NORMAL"
    confidence = max(p_norm, p_anom) * 100.0

    return {
        "result": result,
        "confidence": round(confidence, 1),
        "probabilities": {
            "normal": round(p_norm * 100.0, 1),
            "anomali": round(p_anom * 100.0, 1),
        },
        "key_features": {ch: round(val, 4) for ch, val in zip(CH6, x6)},
        "model_status": "svm_rbf_production",
        "model_metrics": artifact.get("metrics", {}),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Menguji modul predictor...")
    test_normal = {"nm610": 2.5, "nm680": 2.1, "nm730": 6.8, "nm760": 0.5, "nm810": 1.2, "nm860": 0.9}
    res = predict(test_normal)
    print("Hasil Prediksi Uji:", res)
