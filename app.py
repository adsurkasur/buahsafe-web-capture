from __future__ import annotations

import atexit
import csv
import io
import logging
import os
import platform
import re
import sys
import traceback

from flask import Flask, Response, jsonify, render_template, request

import database
from serial_device import (
    CHANNEL_KEYS,
    BuahSafeDevice,
    DeviceError,
    debug_logger,
)

# Konfigurasi standard Python logging dengan format yang jelas dan mudah dibaca
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("buahsafe.server")

app = Flask(__name__)
device = BuahSafeDevice()
FRUIT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")
VALID_LABELS = {"", "bagus", "rusak"}

database.initialize()
atexit.register(device.disconnect)


@app.before_request
def log_request_info():
    if request.path != "/api/debug" and not request.path.startswith("/static"):
        debug_logger.add(
            "DEBUG",
            "API",
            f"{request.method} {request.path}",
            extra={"ip": request.remote_addr, "args": dict(request.args)},
        )


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    return jsonify({
        "device": device.status(),
        "summary": database.summary(),
        "last_raw_line": debug_logger.last_raw_line,
    })


@app.get("/api/ports")
def api_ports():
    ports = device.available_ports()
    return jsonify({"ports": ports})


@app.post("/api/connect")
def api_connect():
    payload = request.get_json(silent=True) or {}
    port = str(payload.get("port", "")).strip()
    if not port:
        err_msg = "Pilih port COM terlebih dahulu"
        debug_logger.add("WARN", "API", f"Connect gagal: {err_msg}")
        return jsonify({"error": err_msg}), 400
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
        err_msg = (
            "ID jambu wajib diisi (maks. 31 karakter; gunakan huruf, "
            "angka, tanda hubung, atau underscore)"
        )
        debug_logger.add("WARN", "API", f"Scan dibatalkan: {err_msg}")
        return jsonify({"error": err_msg}), 400

    reading = device.scan()
    measurement = database.insert_measurement(fruit_id, reading)
    debug_logger.add(
        "INFO",
        "DATABASE",
        f"Record tersimpan ID={measurement['id']} (Buah={fruit_id}, Scan #{measurement['scan_no']})",
    )
    return jsonify({
        "measurement": measurement,
        "summary": database.summary(),
        "raw_line": debug_logger.last_raw_line,
    })


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


@app.get("/api/debug")
def api_debug_logs():
    try:
        limit = int(request.args.get("limit", 150))
    except ValueError:
        limit = 150

    return jsonify({
        "logs": debug_logger.get_logs(limit),
        "last_raw_line": debug_logger.last_raw_line,
        "system": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "os": os.name,
            "port": device.port,
            "connected": device.connected,
            "summary": database.summary(),
        },
    })


@app.post("/api/debug/clear")
def api_debug_clear():
    debug_logger.clear()
    return jsonify({"status": "cleared", "logs": []})


@app.errorhandler(DeviceError)
def handle_device_error(error: DeviceError):
    details = error.to_dict() if hasattr(error, "to_dict") else {"message": str(error)}
    return jsonify({
        "error": str(error),
        "details": details,
        "device": device.status(),
        "last_raw_line": debug_logger.last_raw_line,
    }), 503


@app.errorhandler(Exception)
def handle_general_exception(error: Exception):
    tb = traceback.format_exc()
    debug_logger.add("ERROR", "SERVER", f"Unhandled exception: {error}", extra={"traceback": tb})
    logger.exception("Unhandled server exception:")
    return jsonify({
        "error": f"Server Error: {error}",
        "details": {"traceback": tb, "type": type(error).__name__},
    }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
