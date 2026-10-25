"""ESP32 virtual BuahSafe: meniru firmware buahsafe_wifi/ tanpa perangkat keras.

Bicara dengan server memakai protokol yang SAMA PERSIS dengan firmware:
  GET  /api/device/poll   (long-poll, header X-Device-Key)
  POST /api/device/result {"job", "line": "DATA,<n>,<18 nilai>"} atau {"job", "error"}

Spektrum yang dikirim adalah scan NYATA dari buah holdout (ml/holdout_fruits.json),
yaitu buah yang tidak pernah dipakai melatih model demo, jadi putusan yang muncul
di web adalah uji jujur, bukan hafalan.
  - ID buah yang diketik operator memuat ID buah holdout (mis. BOSOK_004, UJI-BOSOK_004)
    -> putar salah satu rotasi buah itu.
  - ID berawalan GAGAL-  -> laporkan sensor gagal (uji jalur gagal-aman).
  - Selain itu           -> buah holdout acak.

Konfigurasi lewat env: BUAHSAFE_SERVER_URL, BUAHSAFE_DEVICE_KEY.
Cek logika tanpa jaringan: python esp32_simulator.py --check
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "output" / "finalised" / "buahsafe_dataset_gabungan_final.csv"
HOLDOUT = ROOT / "ml" / "holdout_fruits.json"
CHANNELS = ["nm410", "nm435", "nm460", "nm485", "nm510", "nm535", "nm560", "nm585", "nm610",
            "nm645", "nm680", "nm705", "nm730", "nm760", "nm810", "nm860", "nm900", "nm940"]
FIRMWARE = "sim-1.0"
WARMUP_S = 3.0          # pemanasan lampu halogen di firmware asli
HTTP_TIMEOUT_S = 15     # sama dengan firmware
BACKOFF_MAX_S = 30


def load_holdout_scans() -> dict[str, list[dict[str, str]]]:
    fruits = set(json.loads(HOLDOUT.read_text(encoding="utf-8"))["fruits"])
    scans: dict[str, list[dict[str, str]]] = {}
    with open(DATA, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["fruit_id"] in fruits:
                scans.setdefault(row["fruit_id"].upper(), []).append(row)
    return scans


def choose_scan(scans: dict[str, list[dict[str, str]]], fruit_id: str) -> dict[str, str] | None:
    """None = simulasikan sensor gagal."""
    key = fruit_id.strip().upper()
    if key.startswith("GAGAL"):
        return None
    # ID boleh berawalan, mis. UJI-BOSOK_004 (data uji yang nanti dihapus) -> BOSOK_004
    match = next((fruit for fruit in sorted(scans, key=len, reverse=True) if fruit in key), None)
    return random.choice(scans[match or random.choice(sorted(scans))])


class Simulator:
    def __init__(self, server: str, key: str) -> None:
        self.server = server.rstrip("/")
        self.key = key
        self.scans = load_holdout_scans()
        self.scan_no = 0

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        req = urllib.request.Request(
            self.server + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Device-Key": self.key, "Content-Type": "application/json",
                     "User-Agent": f"BuahSafe-ESP32-Simulator/{FIRMWARE}"})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            return err.code, None

    def handle(self, command: dict) -> None:
        job, fruit_id = command["job"], command.get("fruit_id", "")
        row = choose_scan(self.scans, fruit_id)
        time.sleep(WARMUP_S)
        if row is None:
            code, _ = self._request("POST", "/api/device/result", {"job": job, "error": "AS7265X_NOT_READY"})
            print(f"[SCAN] {fruit_id}: simulasi sensor gagal -> HTTP {code}", flush=True)
            return
        self.scan_no += 1
        line = f"DATA,{self.scan_no}," + ",".join(f"{float(row[c]):.6f}" for c in CHANNELS)
        code, resp = self._request("POST", "/api/device/result", {"job": job, "line": line})
        print(f"[SCAN] {fruit_id}: putar {row['fruit_id']} rotasi {row.get('rotasi_buah', '?')} "
              f"(label {row['label']}) -> HTTP {code}, scan_no {(resp or {}).get('scan_no')}", flush=True)

    def run(self) -> None:
        print(f"ESP32 virtual -> {self.server} | {len(self.scans)} buah holdout", flush=True)
        backoff = 1
        while True:
            try:
                code, body = self._request("GET", f"/api/device/poll?fw={FIRMWARE}&rssi=-50&ip=virtual")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                code, body = -1, None
                print(f"[NET] {err}", flush=True)
            if code == 204:
                backoff = 1
            elif code == 200 and body:
                backoff = 1
                self.handle(body)
            else:
                if code == 401:
                    print("[AUTH] Kunci perangkat ditolak server", flush=True)
                    backoff = BACKOFF_MAX_S
                time.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX_S)


def check() -> None:
    scans = load_holdout_scans()
    assert len(scans) == len(json.loads(HOLDOUT.read_text(encoding="utf-8"))["fruits"])
    some = sorted(scans)[0]
    assert choose_scan(scans, some.lower())["fruit_id"].upper() == some
    assert choose_scan(scans, f"UJI-{some}")["fruit_id"].upper() == some
    assert choose_scan(scans, "GAGAL-01") is None
    assert choose_scan(scans, "JB-0001")["fruit_id"].upper() in scans
    print(f"esp32_simulator check OK ({len(scans)} buah holdout)")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        Simulator(os.environ["BUAHSAFE_SERVER_URL"], os.environ["BUAHSAFE_DEVICE_KEY"]).run()
