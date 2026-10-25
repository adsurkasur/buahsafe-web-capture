"""ESP32 virtual BuahSafe (mode conveyor): meniru firmware buahsafe_wifi/ tanpa perangkat keras.

Bicara dengan server memakai protokol yang SAMA dengan firmware conveyor:
  GET  /api/device/poll?fw=sim-...   detak tiap 10 detik (header X-Device-Key)
  POST /api/device/auto-scan         {"line": "DATA,<n>,<18 nilai>", "trigger_ms", "measure_ms"}
                                     atau {"error": "..."} bila sensor gagal

Simulator TIDAK memindai sendiri. Ia hanya mengirim buah bila supervisor/owner
menekan "Jalankan simulasi conveyor" di web (server menitipkan {"simulate": n}
di jawaban detak), sehingga database tidak terisi data simulasi tanpa diminta.

Spektrum yang dikirim adalah scan NYATA dari buah holdout (ml/holdout_fruits.json),
yaitu buah yang tidak pernah dipakai melatih model demo. Jarak antarbuah 3-6 detik
meniru belt; buah ke-7 dalam satu kiriman (bila ada) disimulasikan gagal diukur
supaya jalur "GAGAL - sisihkan" ikut teruji.

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
FIRMWARE = "sim-2.0-conveyor"
HEARTBEAT_S = 10
HTTP_TIMEOUT_S = 15
BACKOFF_MAX_S = 30
FAIL_AT = 7  # urutan buah dalam satu kiriman yang disimulasikan gagal diukur


def load_holdout_scans() -> list[dict[str, str]]:
    fruits = set(json.loads(HOLDOUT.read_text(encoding="utf-8"))["fruits"])
    with open(DATA, encoding="utf-8-sig") as f:
        return [row for row in csv.DictReader(f) if row["fruit_id"] in fruits]


def batch_plan(count: int) -> list[bool]:
    """True = buah diukur normal, False = sensor gagal (buah ke-FAIL_AT)."""
    return [i + 1 != FAIL_AT for i in range(count)]


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
            raw = err.read()
            return err.code, json.loads(raw) if raw else None

    def send_fruit(self, measured: bool) -> None:
        if not measured:
            code, resp = self._request("POST", "/api/device/auto-scan", {"error": "AS7265X_NOT_READY", "fw": FIRMWARE})
            print(f"[BUAH] simulasi sensor gagal -> HTTP {code} {(resp or {}).get('fruit_id')}", flush=True)
            return
        row = random.choice(self.scans)
        self.scan_no += 1
        line = f"DATA,{self.scan_no}," + ",".join(f"{float(row[c]):.6f}" for c in CHANNELS)
        code, resp = self._request("POST", "/api/device/auto-scan", {
            "line": line, "fw": FIRMWARE,
            "trigger_ms": random.randint(600, 1200), "measure_ms": random.randint(450, 650)})
        print(f"[BUAH] putar {row['fruit_id']} (label {row['label']}) -> HTTP {code} "
              f"{(resp or {}).get('fruit_id')} {(resp or {}).get('result')}", flush=True)

    def run(self) -> None:
        print(f"ESP32 virtual conveyor -> {self.server} | {len(self.scans)} scan buah holdout", flush=True)
        backoff = 1
        while True:
            try:
                code, body = self._request("GET", f"/api/device/poll?fw={FIRMWARE}&rssi=-50&ip=virtual")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
                code, body = -1, None
                print(f"[NET] {err}", flush=True)
            if code in (200, 204):
                backoff = 1
                for measured in batch_plan(int((body or {}).get("simulate", 0))):
                    time.sleep(random.uniform(3, 6))  # jarak antarbuah di belt
                    self.send_fruit(measured)
                time.sleep(HEARTBEAT_S)
                continue
            if code == 401:
                print("[AUTH] Kunci perangkat ditolak server", flush=True)
                backoff = BACKOFF_MAX_S
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)


def check() -> None:
    scans = load_holdout_scans()
    fruits = json.loads(HOLDOUT.read_text(encoding="utf-8"))["fruits"]
    assert {r["fruit_id"] for r in scans} == set(fruits)
    assert batch_plan(10).count(False) == 1 and batch_plan(10)[FAIL_AT - 1] is False
    assert all(batch_plan(5))
    print(f"esp32_simulator check OK ({len(fruits)} buah holdout, {len(scans)} scan)")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        Simulator(os.environ["BUAHSAFE_SERVER_URL"], os.environ["BUAHSAFE_DEVICE_KEY"]).run()
