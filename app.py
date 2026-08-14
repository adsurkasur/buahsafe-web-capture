from __future__ import annotations

import atexit
import csv
import io
import re

from flask import Flask, Response, jsonify, render_template, request

import database
from serial_device import CHANNEL_KEYS, BuahSafeDevice, DeviceError

app = Flask(__name__)
device = BuahSafeDevice()
FRUIT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")
VALID_LABELS = {"", "bagus", "rusak"}

database.initialize()
atexit.register(device.disconnect)


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    return jsonify({"device": device.status(), "summary": database.summary()})


@app.get("/api/ports")
def api_ports():
    return jsonify({"ports": device.available_ports()})


@app.post("/api/connect")
def api_connect():
    payload = request.get_json(silent=True) or {}
    port = str(payload.get("port", "")).strip()
    if not port:
        return jsonify({"error": "Pilih port COM terlebih dahulu"}), 400
    device.connect(port)
    return jsonify({"device": device.status()})


@app.post("/api/disconnect")
def api_disconnect():
    device.disconnect()
    return jsonify({"device": device.status()})


@app.post("/api/scan")
def api_scan():
    payload = request.get_json(silent=True) or {}
    fruit_id = str(payload.get("fruit_id", "")).strip().upper()
    if not FRUIT_ID_PATTERN.fullmatch(fruit_id):
        return (
            jsonify(
                {
                    "error": (
                        "ID jambu wajib diisi (maks. 31 karakter; gunakan huruf, "
                        "angka, tanda hubung, atau underscore)"
                    )
                }
            ),
            400,
        )

    reading = device.scan()
    measurement = database.insert_measurement(fruit_id, reading)
    return jsonify({"measurement": measurement, "summary": database.summary()})


@app.get("/api/measurements")
def api_measurements():
    try:
        limit = int(request.args.get("limit", 250))
    except ValueError:
        limit = 250
    return jsonify({"measurements": database.list_measurements(limit)})


@app.patch("/api/measurements/<int:measurement_id>/label")
def api_update_label(measurement_id: int):
    payload = request.get_json(silent=True) or {}
    label = str(payload.get("label", "")).strip().lower()
    if label not in VALID_LABELS:
        return jsonify({"error": "Label harus kosong, bagus, atau rusak"}), 400
    measurement = database.update_label(measurement_id, label)
    if measurement is None:
        return jsonify({"error": "Data tidak ditemukan"}), 404
    return jsonify({"measurement": measurement, "summary": database.summary()})


@app.get("/export.csv")
def export_csv():
    rows = database.all_measurements()
    output = io.StringIO()
    fieldnames = [
        "timestamp",
        "fruit_id",
        "scan_no",
        *CHANNEL_KEYS,
        "label",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=buahsafe_dataset.csv"},
    )


@app.errorhandler(DeviceError)
def handle_device_error(error: DeviceError):
    return jsonify({"error": str(error), "device": device.status()}), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
