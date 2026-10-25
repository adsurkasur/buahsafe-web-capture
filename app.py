from __future__ import annotations

import atexit
import csv
import io
import logging
import os
import platform
import re
import secrets
import sys
import traceback
from functools import wraps
from typing import Any

from flask import Flask, Response, g, jsonify, render_template, request

import database
import predictor
from _version import __version__
from wifi_device import WifiDevice
from serial_device import (
    CHANNEL_KEYS,
    BuahSafeDevice,
    DeviceError,
    debug_logger,
)

# Konfigurasi standard Python logging dengan format yang jelas dan mudah dibaca
logging.basicConfig(
    # Produksi: BUAHSAFE_LOG_LEVEL=INFO supaya journald di flash tidak dibanjiri DEBUG
    level=os.environ.get("BUAHSAFE_LOG_LEVEL", "DEBUG").upper(),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("buahsafe.server")

app = Flask(__name__)
PRODUCTION = os.environ.get("BUAHSAFE_ENV", "").lower() == "production"
# serial (bawaan): ESP32 di USB komputer ini. wifi: ESP32 di mitra, long-poll ke server.
DEVICE_MODE = os.environ.get("BUAHSAFE_DEVICE_MODE", "serial").lower()
DEVICE_KEY = os.environ.get("BUAHSAFE_DEVICE_KEY", "")
device = WifiDevice(os.environ.get("BUAHSAFE_DEVICE_ID", "BSF-001")) if DEVICE_MODE == "wifi" else BuahSafeDevice()
FRUIT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,30}$")
VALID_LABELS = {"", "normal", "anomali"}
VALID_ROTASI = {"", "A", "B", "C", "D"}
MAX_DIAMETER_CM = 50.0
MAX_JARAK_CM = 100.0
CORS_ORIGINS = {
    o.strip().rstrip("/")
    for o in os.environ.get(
        "BUAHSAFE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
}

database.initialize()
if DEVICE_MODE == "wifi" and os.environ.get("BUAHSAFE_DEVICE_LABEL"):
    # Mis. "Meja Sortasi (Simulator)" agar data demo tidak tertukar dengan alat asli
    database.set_device_name(device.device_id, os.environ["BUAHSAFE_DEVICE_LABEL"])
# Muat model saat start: muat-pertama scikit-learn dari HDD server bisa >10 s dan
# membuat scan pertama melewati batas tunggu ESP32/klien.
predictor.load_model()
atexit.register(device.disconnect)


def _get_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return None


def require_auth(allowed_roles: list[str] | tuple[str, ...] | None = None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = _get_bearer_token()
            if not token:
                return jsonify({"error": "Sesi tidak ditemukan. Silakan masuk terlebih dahulu."}), 401
            session = database.validate_session_token(token)
            if not session:
                return jsonify({"error": "Sesi telah berakhir atau tidak valid. Silakan masuk kembali."}), 401
            g.current_user = session
            if allowed_roles and session.get("role") not in allowed_roles:
                return jsonify({
                    "error": f"Akses ditolak. Fitur ini memerlukan hak akses: {', '.join(allowed_roles)}.",
                    "required_roles": list(allowed_roles),
                    "current_role": session.get("role"),
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# Di produksi server terbuka ke internet (Cloudflare Tunnel): endpoint warisan dasbor
# akuisisi lokal yang tadinya tanpa token ikut diwajibkan login di sini.
PUBLIC_PATHS = {"/api/auth/login", "/api/auth/logout", "/api/device/poll", "/api/device/result"}


@app.before_request
def enforce_production_auth():
    if not PRODUCTION or request.method == "OPTIONS" or request.path in PUBLIC_PATHS:
        return None
    if request.path == "/":
        # Dasbor akuisisi USB lokal tidak dilayani di server produksi
        return jsonify({"error": "Halaman atau endpoint tidak ditemukan"}), 404
    if not (request.path.startswith("/api/") or request.path == "/export.csv"):
        return None
    session = database.validate_session_token(_get_bearer_token() or "")
    if not session:
        return jsonify({"error": "Sesi tidak ditemukan. Silakan masuk terlebih dahulu."}), 401
    g.current_user = session
    if request.method != "GET" and session.get("role") == "operator" and request.path != "/api/scan":
        return jsonify({"error": "Akses ditolak untuk peran operator."}), 403
    return None


@app.before_request
def log_request_info():
    if request.path not in ("/api/debug", "/api/device/poll") and not request.path.startswith("/static"):
        debug_logger.add(
            "DEBUG",
            "API",
            f"{request.method} {request.path}",
            extra={"ip": request.remote_addr, "args": dict(request.args)},
        )


@app.after_request
def add_cors_headers(response: Response) -> Response:
    """Izinkan CORS hanya untuk origin klien yang terdaftar (BUAHSAFE_CORS_ORIGINS).

    Wildcard "*" membuat situs mana pun yang dibuka di peramban operator bisa membaca
    data dan mengubah label dataset lewat endpoint lokal yang tidak memerlukan token.
    """
    origin = request.headers.get("Origin", "")
    response.headers["Vary"] = "Origin"
    if origin not in CORS_ORIGINS:
        return response
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.route("/api/<path:subpath>", methods=["OPTIONS"])
def api_options(subpath: str):
    """Preflight handler untuk CORS."""
    return "", 204


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    # Browser otomatis minta ini; jawab kosong supaya tidak membanjiri log/404 handler.
    return "", 204


@app.get("/api/status")
def api_status():
    return jsonify({
        "version": __version__,
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
@require_auth(["operator", "supervisor", "owner"])
def api_scan():
    payload = request.get_json(silent=True) or {}
    fruit_id = str(payload.get("fruit_id", "")).strip().upper()
    device_id = str(payload.get("device_id", "BSF-001")).strip()
    operator_id = str(payload.get("operator_id", "")).strip() or getattr(g, "current_user", {}).get("name", "")

    if not FRUIT_ID_PATTERN.fullmatch(fruit_id):
        err_msg = (
            "ID jambu wajib diisi (maks. 31 karakter; gunakan huruf, "
            "angka, tanda hubung, atau underscore)"
        )
        debug_logger.add("WARN", "API", f"Scan dibatalkan: {err_msg}")
        return jsonify({"error": err_msg}), 400

    reading = device.scan(fruit_id) if isinstance(device, WifiDevice) else device.scan()

    # Eksekusi inferensi Machine Learning SVM (RBF)
    try:
        prediction_result = predictor.predict(reading)
    except Exception as pred_err:
        # Gagal-aman: jangan pernah mengarang putusan NORMAL. Spektrum tetap disimpan
        # (tanpa prediksi) agar data tidak hilang, lalu operator diarahkan ke pemeriksaan manual.
        logger.warning("Inferensi ML gagal: %s", pred_err)
        measurement = database.insert_measurement(
            fruit_id=fruit_id,
            reading=reading,
            device_id=device_id or "BSF-001",
            operator_id=operator_id or "",
        )
        device.notify_saved(measurement["scan_no"])
        debug_logger.add("ERROR", "ML", f"Inferensi gagal untuk {fruit_id} (record ID={measurement['id']}): {pred_err}")
        return jsonify({
            "error": "Model klasifikasi tidak dapat memproses pindaian ini. "
                     "Pisahkan buah untuk pemeriksaan manual, lalu hubungi Supervisor QC.",
            "measurement": measurement,
        }), 503

    measurement = database.insert_measurement(
        fruit_id=fruit_id,
        reading=reading,
        prediction=prediction_result.get("result", ""),
        confidence=prediction_result.get("confidence"),
        device_id=device_id or "BSF-001",
        operator_id=operator_id or "",
    )
    debug_logger.add(
        "INFO",
        "DATABASE",
        f"Record tersimpan ID={measurement['id']} (Buah={fruit_id}, Scan #{measurement['scan_no']}, Prediksi={prediction_result.get('result')})",
    )
    # Beri tahu firmware scan_no yang SAH (dari database) supaya LCD sinkron.
    device.notify_saved(measurement["scan_no"])
    return jsonify({
        "measurement": measurement,
        "prediction": prediction_result,
        "summary": database.summary(),
        "raw_line": debug_logger.last_raw_line,
    })


@app.post("/api/predict")
def api_predict():
    """Endpoint inferensi ML mandiri dari data spektral (berguna untuk testing web/Vercel)."""
    payload = request.get_json(silent=True) or {}
    spectral = payload.get("spectral", payload)
    try:
        res = predictor.predict(spectral)
        return jsonify(res)
    except Exception as err:
        return jsonify({"error": str(err)}), 400


@app.post("/api/auth/login")
def api_auth_login():
    """Autentikasi peran pengguna dengan kata sandi PBKDF2 bergaram dan penerbitan token sesi 24 jam."""
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"ok": False, "error": "Nama pengguna dan kata sandi wajib diisi"}), 400

    user, error = database.authenticate_user(username, password)
    if error or not user:
        debug_logger.add("WARN", "AUTH", f"Percobaan masuk gagal untuk '{username}': {error}")
        return jsonify({"ok": False, "error": error or "Nama pengguna atau kata sandi tidak cocok"}), 401

    token = database.create_session_token(user["id"], user["role"], hours=24)
    debug_logger.add("INFO", "AUTH", f"Pengguna '{user['username']}' ({user['role']}) berhasil masuk")
    return jsonify({
        "ok": True,
        "token": token,
        "user": user,
    })


@app.post("/api/auth/logout")
def api_auth_logout():
    """Pencabutan token sesi saat pengguna keluar."""
    token = _get_bearer_token()
    if not token:
        payload = request.get_json(silent=True) or {}
        token = payload.get("token")
    if token:
        database.revoke_session_token(token)
    return jsonify({"ok": True, "message": "Berhasil keluar dari sesi"})


@app.get("/api/auth/me")
@require_auth()
def api_auth_me():
    """Memperoleh data profil sesi aktif pengguna saat ini."""
    return jsonify({"ok": True, "user": g.current_user})


@app.get("/api/users")
@require_auth(["owner"])
def api_get_users():
    """Daftar pengguna sistem (khusus Owner)."""
    return jsonify({"users": database.list_users()})


@app.post("/api/users")
@require_auth(["owner"])
def api_create_user():
    """Membuat pengguna baru dalam sistem (khusus Owner)."""
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", ""))
    name = str(payload.get("name", ""))
    password = str(payload.get("password", ""))
    role = str(payload.get("role", ""))

    user, err = database.create_user(username, name, password, role)
    if err:
        return jsonify({"error": err}), 400
    debug_logger.add("INFO", "USER_MGMT", f"Pengguna baru dibuat: {username} ({role}) oleh {g.current_user['username']}")
    return jsonify({"ok": True, "user": user}), 201


@app.put("/api/users/<user_id>/password")
@require_auth(["owner"])
def api_update_user_password(user_id: str):
    """Mereset kata sandi akun pengguna (khusus Owner)."""
    payload = request.get_json(silent=True) or {}
    new_password = str(payload.get("password", ""))
    ok, err = database.update_user_password(user_id, new_password)
    if not ok:
        return jsonify({"error": err or "Gagal memperbarui kata sandi"}), 400
    debug_logger.add("INFO", "USER_MGMT", f"Kata sandi pengguna {user_id} diperbarui oleh {g.current_user['username']}")
    return jsonify({"ok": True, "message": "Kata sandi berhasil diperbarui"})


@app.delete("/api/users/<user_id>")
@require_auth(["owner"])
def api_delete_user(user_id: str):
    """Menonaktifkan pengguna dari sistem (khusus Owner)."""
    if user_id == g.current_user.get("id"):
        return jsonify({"error": "Tidak dapat menghapus akun Anda sendiri yang sedang aktif"}), 400
    ok = database.delete_user(user_id)
    if not ok:
        return jsonify({"error": "Pengguna tidak ditemukan atau sudah tidak aktif"}), 404
    debug_logger.add("INFO", "USER_MGMT", f"Pengguna {user_id} dinonaktifkan oleh {g.current_user['username']}")
    return jsonify({"ok": True, "message": "Pengguna berhasil dinonaktifkan"})


@app.get("/api/devices")
def api_devices():
    """Daftar status armada pemindai BuahSafe."""
    devices = database.list_devices()
    if DEVICE_MODE == "wifi":
        # Status alat WiFi diambil dari detak long-poll, bukan kolom DB yang bisa basi
        for d in devices:
            if d["id"] == device.device_id:
                d["status"] = "online" if device.connected else "offline"
    return jsonify({"devices": devices})


def _device_authorized() -> bool:
    key = request.headers.get("X-Device-Key", "")
    return bool(DEVICE_KEY) and secrets.compare_digest(key.encode(), DEVICE_KEY.encode())


@app.get("/api/device/poll")
def api_device_poll():
    """Long-poll ESP32 (mode WiFi): tunggu perintah scan hingga ~10 detik."""
    if DEVICE_MODE != "wifi":
        return jsonify({"error": "Server tidak berjalan dalam mode WiFi"}), 404
    if not _device_authorized():
        return jsonify({"error": "Kunci perangkat tidak valid"}), 401
    command = device.poll({k: request.args.get(k) for k in ("fw", "rssi", "ip")})
    if command is None:
        return "", 204
    return jsonify(command)


@app.post("/api/device/result")
def api_device_result():
    """Hasil scan dari ESP32: {"job", "line": "DATA,..."} atau {"job", "error"}."""
    if DEVICE_MODE != "wifi":
        return jsonify({"error": "Server tidak berjalan dalam mode WiFi"}), 404
    if not _device_authorized():
        return jsonify({"error": "Kunci perangkat tidak valid"}), 401
    payload = request.get_json(silent=True) or {}
    accepted, scan_no = device.submit(
        str(payload.get("job", "")), payload.get("line"), payload.get("error")
    )
    if not accepted:
        return jsonify({"ok": False, "error": "Job kedaluwarsa"}), 409
    return jsonify({"ok": True, "scan_no": scan_no})


@app.get("/api/analytics")
def api_analytics():
    """Metrik analitik real-time dari database untuk supervisor/owner."""
    return jsonify(database.get_analytics_summary())


@app.get("/api/master-data/petani")
def api_get_petani():
    """Daftar petani mitra untuk owner."""
    return jsonify({"petani": database.list_petani()})


@app.post("/api/master-data/petani")
@require_auth(["owner"])
def api_add_petani():
    """Tambah petani mitra baru."""
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Nama petani wajib diisi"}), 400
    village = str(payload.get("village", ""))
    phone = str(payload.get("phone", ""))
    petani = database.add_petani(name, village, phone)
    return jsonify({"petani": petani}), 201


@app.delete("/api/master-data/petani/<petani_id>")
@require_auth(["owner"])
def api_delete_petani(petani_id: str):
    """Hapus petani mitra."""
    deleted = database.delete_petani(petani_id)
    if not deleted:
        return jsonify({"error": "Petani tidak ditemukan"}), 404
    return jsonify({"deleted_id": petani_id})


@app.get("/api/measurements")
def api_measurements():
    try:
        limit = int(request.args.get("limit", 250))
    except ValueError:
        limit = 250
    try:
        offset = int(request.args.get("offset", 0))
    except ValueError:
        offset = 0
    search = str(request.args.get("q", "")).strip()
    label = str(request.args.get("label", "")).strip().lower()
    if label not in VALID_LABELS:
        label = ""

    measurements = database.list_measurements(limit, offset, search, label)
    total = database.count_measurements(search, label)
    return jsonify({
        "measurements": measurements,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.delete("/api/measurements/<int:measurement_id>")
@require_auth(["supervisor", "owner"])
def api_delete_measurement(measurement_id: int):
    deleted = database.delete_measurement(measurement_id)
    if not deleted:
        return jsonify({"error": "Data tidak ditemukan"}), 404
    debug_logger.add("INFO", "DATABASE", f"Record dihapus ID={measurement_id}")
    return jsonify({"deleted_id": measurement_id, "summary": database.summary()})


@app.post("/api/measurements/bulk-delete")
@require_auth(["supervisor", "owner"])
def api_bulk_delete_measurements():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "Pilih minimal satu data untuk dihapus"}), 400
    try:
        clean_ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({"error": "Daftar ID tidak valid"}), 400

    deleted_count = database.delete_measurements(clean_ids)
    debug_logger.add(
        "INFO", "DATABASE",
        f"Bulk delete: {deleted_count} record dihapus (diminta {len(clean_ids)})",
    )
    return jsonify({"deleted_count": deleted_count, "summary": database.summary()})


@app.delete("/api/measurements")
@require_auth(["owner"])
def api_reset_measurements():
    deleted_count = database.reset_all_measurements()
    debug_logger.add(
        "WARN", "DATABASE",
        f"RESET DATABASE: {deleted_count} record dihapus (seluruh data, counter direset)",
    )
    return jsonify({"deleted_count": deleted_count, "summary": database.summary()})


@app.patch("/api/measurements/<int:measurement_id>/label")
def api_update_label(measurement_id: int):
    payload = request.get_json(silent=True) or {}
    label = str(payload.get("label", "")).strip().lower()
    if label not in VALID_LABELS:
        return jsonify({"error": "Label harus kosong, normal, atau anomali"}), 400
    measurement = database.update_label(measurement_id, label)
    if measurement is None:
        return jsonify({"error": "Data tidak ditemukan"}), 404
    return jsonify({"measurement": measurement, "summary": database.summary()})


def _parse_manual_measurement(raw: Any, field_label: str, max_value: float) -> tuple[float | None, str | None]:
    """Parse input angka manual (diameter/jarak) dari operator.

    Nilai kosong ("" atau None) berarti belum diukur -> dikembalikan sebagai
    None (bukan error). Selain itu harus berupa angka positif yang masuk akal
    (0 < x <= max_value) supaya salah ketik tidak lolos ke dataset.
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, f"{field_label} harus berupa angka"
    if value <= 0 or value > max_value:
        return None, f"{field_label} harus antara 0 dan {max_value:g} cm"
    return value, None


@app.patch("/api/measurements/<int:measurement_id>/diameter")
def api_update_diameter(measurement_id: int):
    payload = request.get_json(silent=True) or {}
    value, error = _parse_manual_measurement(payload.get("diameter_cm"), "Diameter", MAX_DIAMETER_CM)
    if error:
        debug_logger.add("WARN", "API", f"Update diameter gagal: {error}")
        return jsonify({"error": error}), 400
    measurement = database.update_diameter(measurement_id, value)
    if measurement is None:
        return jsonify({"error": "Data tidak ditemukan"}), 404
    return jsonify({"measurement": measurement, "summary": database.summary()})


@app.patch("/api/measurements/<int:measurement_id>/rotasi-sensor")
def api_update_rotasi_sensor(measurement_id: int):
    payload = request.get_json(silent=True) or {}
    rotasi = str(payload.get("rotasi_sensor", "")).strip().upper()
    if rotasi not in VALID_ROTASI:
        return jsonify({"error": "Rotasi Sensor harus kosong, A, B, C, atau D"}), 400
    measurement = database.update_rotasi_sensor(measurement_id, rotasi)
    if measurement is None:
        return jsonify({"error": "Data tidak ditemukan"}), 404
    return jsonify({"measurement": measurement, "summary": database.summary()})


@app.patch("/api/measurements/<int:measurement_id>/rotasi-buah")
def api_update_rotasi_buah(measurement_id: int):
    payload = request.get_json(silent=True) or {}
    rotasi = str(payload.get("rotasi_buah", "")).strip().upper()
    if rotasi not in VALID_ROTASI:
        return jsonify({"error": "Rotasi Buah harus kosong, A, B, C, atau D"}), 400
    measurement = database.update_rotasi_buah(measurement_id, rotasi)
    if measurement is None:
        return jsonify({"error": "Data tidak ditemukan"}), 404
    return jsonify({"measurement": measurement, "summary": database.summary()})


@app.patch("/api/measurements/<int:measurement_id>/jarak")
def api_update_jarak(measurement_id: int):
    payload = request.get_json(silent=True) or {}
    value, error = _parse_manual_measurement(payload.get("jarak_cm"), "Jarak", MAX_JARAK_CM)
    if error:
        debug_logger.add("WARN", "API", f"Update jarak gagal: {error}")
        return jsonify({"error": error}), 400
    measurement = database.update_jarak(measurement_id, value)
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
        "diameter_cm",
        "rotasi_sensor",
        "rotasi_buah",
        "jarak_cm",
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
            "version": __version__,
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


@app.errorhandler(404)
def handle_not_found(error):
    # Permintaan seperti /favicon.ico dari browser itu normal, bukan bug -- jangan
    # dicatat sebagai ERROR di debug console supaya log tidak bising/menyesatkan.
    if request.path != "/favicon.ico":
        debug_logger.add("WARN", "API", f"404 pada {request.method} {request.path}")
    return jsonify({"error": "Halaman atau endpoint tidak ditemukan"}), 404


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
    if PRODUCTION:
        # Traceback hanya di log server; jangan bocorkan path/kode ke klien publik
        return jsonify({"error": "Terjadi galat di server. Hubungi admin BuahSafe."}), 500
    return jsonify({
        "error": f"Server Error: {error}",
        "details": {"traceback": tb, "type": type(error).__name__},
    }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
