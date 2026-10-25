# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - 2026-10-25 (conveyor)
### Added
- Mode conveyor: `/api/device/auto-scan`, `/api/device/simulate`, detak perangkat, nomor urut harian buah.
- Firmware conveyor v2.1.0 (PIR GPIO 27, relay GPIO 4, buzzer berpola).
- `ml/evaluate_models.py --data` untuk melatih ulang dengan scan conveyor berlabel.

### Changed
- ESP32 virtual meniru conveyor dan hanya mengirim buah atas permintaan web.
- Ekspor CSV tidak memuat baris penanda `GAGAL`.

## [Unreleased] - 2026-10-25
### Added
- ESP32 virtual (`esp32_simulator.py`) + `buahsafe-sim.service`.
- Evaluasi ML adil (`ml/evaluate_models.py`) dan generator bahan laporan (`ml/report_materials.py`).
- Backup harian database (`deploy/backup_db.py`, `buahsafe-backup.timer`).

### Changed
- Model produksi: SVM-RBF 18 kanal dengan ambang anomali 0,45 dari artefak (`models/buahsafe_model.joblib`).
- Respons poll perangkat membawa `fruit_id`; nama perangkat bisa diatur lewat `BUAHSAFE_DEVICE_LABEL`.

### Fixed
- Alat yang mati di tengah long-poll tidak lagi terhitung hidup 10 detik lebih lama.

### Removed
- `export_model.py` dan model 6 kanal lama.

## [Unreleased] - 2026-10-23 (server WiFi)
### Added
- Mode perangkat WiFi (`BUAHSAFE_DEVICE_MODE=wifi`) dengan endpoint `/api/device/poll` dan `/api/device/result`.
- Firmware `buahsafe_wifi/` untuk ESP32 WiFi + HTTPS + WiFiManager.
- Mode produksi `BUAHSAFE_ENV=production`: semua API wajib login, traceback disembunyikan.
- Panduan `docs/DEPLOY_SERVER_WIFI.md`.

### Changed
- `requirements.txt` kini lengkap dan dikunci untuk Python 3.14 (sebelumnya hanya Flask dan pyserial).
- Model ML dimuat saat server start.
- DB baru hanya berisi perangkat BSF-001.

## [Unreleased] - 2026-10-23
### Security
- CORS dibatasi ke `BUAHSAFE_CORS_ORIGINS` (sebelumnya `*`).
- Token sesi tidak lagi diterima lewat query string `?token=` (bocor ke log debug publik).

### Fixed
- Kegagalan model ML pada `/api/scan` kini 503 dengan arahan pemeriksaan manual, bukan `NORMAL` 50%.
- `predictor.predict` menolak berjalan tanpa model terlatih, tidak lagi memakai heuristik tebakan.
- Suite uji tidak lagi menulis ke `data/buahsafe.db`; `BUAHSAFE_DB_PATH` mengarahkan ke DB sementara.
- Analitik: satu putusan per baris dan tingkat kelolosan hanya dari baris yang punya putusan.

## [1.4.0] - 2026-10-22
### Added
- Cryptographic password hashing (`PBKDF2-HMAC-SHA256`, 100,000 iterations, 16-byte random salt) in `database.py`.
- SQLite `auth_tokens` table for 24-hour Bearer session tokens with instant token revocation on logout.
- `@require_auth` role-based decorator in `app.py` protecting sensitive and operational endpoints.
- User management API for Owner: `GET /api/users`, `POST /api/users`, `PUT /api/users/<id>/password`, `DELETE /api/users/<id>`.
- Production authentication test suite `test_auth_production.py` (8 automated security tests).

### Changed
- `app.py` login endpoint now issues 24-hour Bearer tokens and authenticates against PBKDF2 hashes.
- Protected `POST /api/scan`, `POST /api/master-data/petani`, `DELETE /api/master-data/petani/<id>`, and `DELETE /api/measurements` with appropriate role requirements.
- Updated `tests/test_app.py`, `tests/test_server_api.py`, and `test_sandbox_e2e.py` to use authenticated headers.
- Integrated auth test suite into orchestrator `run_local_sandbox.py --test`.

## [1.3.0] - 2026-10-22
### Added
- Dedicated Machine Learning prediction module `predictor.py` loading serialized SVM (RBF) 6-channel pipeline (`models/buahsafe_model_svm_6ch.joblib`).
- Export script `export_model.py` training on 518-sample final dataset.
- Standalone ML inference endpoint `POST /api/predict`.
- Multi-role and operations endpoints: `POST /api/auth/login`, `GET /api/devices`, `GET /api/analytics`, and CRUD for `/api/master-data/petani`.
- Native CORS preflight and headers to allow web apps hosted on Vercel to access the server.
- Unit test suite `tests/test_server_api.py` covering CORS, auth, ML inference, devices, and analytics.
- Automated sandbox integration testing suite `test_sandbox_e2e.py` validating the entire local-first workflow without physical sensor dependency.

### Changed
- `app.py` `/api/scan` now automatically runs real-time SVM ML inference and saves predictions (`NORMAL` or `ANOMALI`) with confidence scores.
- `database.py` schema extended with non-destructive migrations for `prediction`, `confidence`, `device_id`, and `operator_id`.
- Seeded default tables for `users`, `devices`, and `petani_mitra`.
- Fixed `test_export_csv_format` in `tests/test_app.py`.

## [1.2.0] - 2026-09-19
### Changed
- Finalised dataset alignment (518 scans, 65 objects).

## [1.0.0] - 2026-09-16
### Added
- Modular logging protocol (`logs/` directory with activity, decision, and changelog files).
- Mandatory `AGENTS.md` guidelines for AI agents and contributors.
