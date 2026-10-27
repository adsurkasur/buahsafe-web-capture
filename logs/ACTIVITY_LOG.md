# Activity Log

### [2026-10-27 09:30] [Claude Code]
- **Goal**: Firmware ESP32 conveyor yang representatif dengan semua parameter bisa diatur untuk penyetelan di alat jadi, selaras dengan API server.
- **Actions**: Firmware 2.2.0-conveyor: semua pin, waktu, sensor, LCD, buzzer, dan detak bisa ditimpa di `config.h`; kenop baru `LAMP_MODE` (nyala saat picu / nyala terus), `MEASURE_SAMPLES` (rata-rata per buah), `DETECT_BEEP`; baris `CFG` saat boot dan `DATA`/`WAKTU`/`HASIL` per buah di Serial; setelan (`settle_ms`, `samples`, `lamp_mode`) ikut dikirim ke `/api/device/auto-scan` dan dicatat di log server. Ditemukan selisih jeda lampu: dataset 3000 ms, conveyor 300 ms; prosedur pemeriksaan ditambahkan ke `docs/DEPLOY_SERVER_WIFI.md`. Gain dan integrasi tetap sama dengan firmware dataset.
- **Files Modified**: `buahsafe_wifi/{buahsafe_wifi.ino,config.example.h}`, `app.py`, `tests/test_conveyor.py`, `docs/DEPLOY_SERVER_WIFI.md`, `logs/*`.
- **Verification**: Firmware terkompilasi dengan nilai bawaan dan dengan `LAMP_MODE=1 MEASURE_SAMPLES=3 TRIGGER_ACTIVE_LEVEL=LOW`; tes baru meniru badan permintaan firmware dan pembacaan `jsonField()` (panjang teks LCD ≤ 16); seluruh tes server lulus.

### [2026-10-26 14:00] [Claude Code]
- **Goal**: Dokumen laporan tersedia sebagai DOCX yang rapi.
- **Actions**: Konversi Markdown ke DOCX dipisah ke `ml/md_docx.py` (dipakai `report_materials.py` dan bisa dijalankan langsung untuk berkas md lain); isi sel tabel kini diformat (tebal/miring, baris judul tebal); daftar bernomor didukung dengan nomor teks agar tidak bersambung antardaftar; butir bersarang memakai List Bullet 2.
- **Files Modified**: `ml/md_docx.py` (baru), `ml/report_materials.py`, `logs/ACTIVITY_LOG.md`.
- **Verification**: Tiga DOCX dibangkitkan; tidak ada sisa markup di paragraf maupun tabel; tampilan diperiksa lewat render PDF LibreOffice.

### [2026-10-26 13:00] [Claude Code]
- **Goal**: Model dan bahan laporan diselaraskan dengan desain penelitian: hanya 6 kanal NIR (610-860 nm, setara sensor AS7263 yang rusak).
- **Actions**: `ml/evaluate_models.py` memilih model hanya dari kandidat 6 kanal (`MAIN_SET`); 18 kanal tetap dinilai sebagai pembanding. Hasil: SVM-RBF 6 kanal, C 100, gamma scale, ambang 0,35; uji independen akurasi 73,1%, recall 66,7%, ROC-AUC 0,724; kepentingan kanal teratas 730 dan 810 nm. `ml/report_materials.py`: spektrum dan PCA memakai kanal model, tabel kandidat utama di atas pembanding, teks dan diagram tidak lagi menulis 18 kanal atau ambang tetap. Kanal 485 nm tercatat bernilai 0 pada 463/518 pemindaian. Firmware: baris kedua LCD menampilkan keyakinan model (sebelumnya mengulang putusan). Tes ambang dibuat tidak bergantung pada model aktif.
- **Files Modified**: `ml/evaluate_models.py`, `ml/report_materials.py`, `ml/output/*`, `models/buahsafe_model.joblib`, `buahsafe_wifi/buahsafe_wifi.ino`, `docs/DEPLOY_SERVER_WIFI.md`, `tests/test_server_api.py`, `logs/*`.
- **Verification**: 77 unit + 9 auth + E2E sandbox lulus; `esp32_simulator.py --check` OK (holdout tetap 13 buah yang sama); firmware terkompilasi.

### [2026-10-26 10:30] [Claude Code]
- **Goal**: Pemilik dapat memutus dan menyambungkan kembali alat dari web; label LCD diselaraskan dengan web.
- **Actions**: Tabel `app_settings` + `get_setting`/`set_setting`; `POST /api/device/enabled` (pemilik saja); detak dan auto-scan ditolak 423 saat alat diputus, status langsung offline (`WifiDevice.mark_offline`); `/api/status` memuat `device.enabled`. Firmware: LCD "Alat diputus / oleh pemilik" pada 423; hasil di LCD menjadi NORMAL / ANOMALI / "GAGAL: sisihkan".
- **Files Modified**: `app.py`, `database.py`, `wifi_device.py`, `buahsafe_wifi/buahsafe_wifi.ino`, `tests/test_conveyor.py`, `logs/*`.
- **Verification**: 77 unit (tes baru `test_owner_can_disconnect_device`) + 9 auth + 6 E2E lulus; firmware terkompilasi (ESP32 Dev Module, 1,18 MB).

### [2026-10-26 01:45] [Claude Code]
- **Goal**: Teks bahan laporan ML ke ragam akademik.
- **Actions**: Templat teks `HASIL_ML.md` di `ml/report_materials.py` ditulis ulang ke ragam ilmiah dengan sitasi metode dan Daftar Pustaka (dikerjakan sesi paralel "ragam akademik"); perhitungan tidak berubah. Seluruh DOI diverifikasi lewat Crossref (15/15).
- **Files Modified**: `ml/report_materials.py`, `logs/ACTIVITY_LOG.md`.
- **Verification**: Generator dijalankan ulang; angka di md/docx/xlsx sama dengan `ml/output/selection_result.json`.

### [2026-10-25 23:30] [Claude Code]
- **Goal**: Menyesuaikan sistem dengan alat sebenarnya: belt conveyor berjalan terus, sensor PIR memicu lampu dan satu pengukuran per buah, operator memilah di ujung belt.
- **Actions**:
  - Server: mode `BUAHSAFE_DEVICE_MODE=conveyor`; `POST /api/device/auto-scan` (ID `CV-YYYYMMDD-NNNN` berurutan, `SIM-` untuk simulator, prediksi + simpan, gagal-aman); laporan buah gagal tetap memakai nomor urut (baris `GAGAL` dikecualikan dari ekspor); detak lewat `/api/device/poll`; `POST /api/device/simulate` (supervisor/owner); `/api/scan` manual 409 di mode conveyor; `trigger_ms`/`measure_ms` dicatat untuk kalibrasi; `/api/device/auto-scan` ditambahkan ke jalur perangkat pada guard produksi (ditemukan oleh tes).
  - Firmware `buahsafe_wifi/` v2.1.0-conveyor: pin sesuai draf (PIR 27, relay 4), pemicu lewat interrupt, buzzer non-blocking (NORMAL 1 bip, ANOMALI 3 bip panjang, GAGAL 2 bip berulang), picu yang terlambat dilaporkan GAGAL, kenop `LAMP_SETTLE_MS`/`TRIGGER_*`/`RELAY_ACTIVE_LOW` di `config.h`.
  - `esp32_simulator.py` mode conveyor: detak; kirim N buah holdout hanya atas permintaan web; buah ke-7 gagal.
  - `ml/evaluate_models.py --data`; `ml/report_materials.py`: tabel tukar-ganti ambang satu scan, keterbatasan buah diam vs bergerak, diagram alur conveyor.
  - Dokumen: `docs/DEPLOY_SERVER_WIFI.md` (arsitektur conveyor, pin, pesan LCD, kalibrasi).
- **Files Modified**: `app.py`, `database.py`, `wifi_device.py`, `esp32_simulator.py`, `buahsafe_wifi/{buahsafe_wifi.ino,config.example.h}`, `ml/{evaluate_models,report_materials}.py`, `tests/test_conveyor.py` (baru), `docs/DEPLOY_SERVER_WIFI.md`, `logs/*`.
- **Verification**: 76 unit (7 tes conveyor baru) + 9 auth + 6 E2E lulus; `esp32_simulator.py --check`; firmware terkompilasi (ESP32 Dev Module, 1,18 MB). Uji langsung: `../LAPORAN_UJI_PENUH_2026-10-25.md`.

### [2026-10-25 22:00] [Claude Code]
- **Goal**: Pengujian penuh BuahSafe dengan ESP32 virtual di mini PC, evaluasi ML yang adil, dan bahan ML untuk laporan akhir.
- **Actions**:
  - `ml/evaluate_models.py` (baru): holdout 13 buah (stratifikasi, per buah), validasi silang bersarang (luar 5, dalam 4, StratifiedGroupKFold) untuk LR/SVM/RF x 6/18 kanal, pemilihan F1, ambang anomali dari prediksi out-of-fold (recall >= 0,80), uji sekali di holdout, ekspor `models/buahsafe_model.joblib`; `--full` melatih ulang 100%. Terpilih SVM-RBF 18 kanal (F1 nested 0,785), ambang 0,45; holdout: akurasi 0,702, recall 0,625, AUC 0,809; 12/13 buah benar bila 8 sisi dirata-ratakan.
  - `predictor.py` membaca kanal dan ambang dari artefak; `export_model.py` dan model 6 kanal lama dihapus.
  - `esp32_simulator.py` (baru): protokol firmware, memutar scan buah holdout; ID memuat ID holdout -> buah itu; `GAGAL-` -> sensor gagal. Poll kini membawa `fruit_id`; label perangkat dari `BUAHSAFE_DEVICE_LABEL`.
  - `wifi_device.py`: detak perangkat tidak lagi diperbarui setelah long-poll menunggu (alat mati terdeteksi 10 s lebih cepat; ditemukan saat uji).
  - `deploy/`: unit systemd API, simulator, backup harian + `backup_db.py` (integrity_check, simpan 14 hari).
  - `ml/report_materials.py` (baru): 10 gambar 300 dpi, `hasil_ml.xlsx`, `HASIL_ML.md/.docx`, DOCX penjelasan awam di `../bahan-laporan-ml/`.
  - Server t530: model baru, simulator, backup terpasang; CORS `https://buahsafe.vercel.app`.
- **Files Modified**: `predictor.py`, `wifi_device.py`, `app.py`, `database.py`, `esp32_simulator.py`, `ml/*`, `deploy/*`, `models/buahsafe_model.joblib`, `tests/test_server_api.py`, `tests/test_wifi_production.py`, `test_sandbox_e2e.py`, `docs/DEPLOY_SERVER_WIFI.md`, `logs/*`; dihapus `export_model.py`, `models/buahsafe_model_svm_6ch.joblib`.
- **Verification**: 69 unit + 9 auth + 6 E2E + build lulus; `esp32_simulator.py --check`; prediksi server = lokal 20/20; uji peramban di buahsafe.vercel.app 28/28; uji API 15/15; backup + restore lolos. Rincian: `../LAPORAN_UJI_PENUH_2026-10-25.md`.

### [2026-10-23 16:30] [Claude Code]
- **Goal**: Menjalankan BuahSafe di server HP t530 Thin Client (`adsur@192.168.1.10`) dengan ESP32 di mitra tersambung lewat WiFi; production ready untuk satu set perangkat.
- **Actions**:
  - `wifi_device.py` (baru): transport WiFi berbasis long-poll dengan antarmuka sama dengan `BuahSafeDevice`; endpoint `GET /api/device/poll` dan `POST /api/device/result` berkunci `X-Device-Key`.
  - `app.py`: `BUAHSAFE_DEVICE_MODE`, `BUAHSAFE_ENV=production` (semua API wajib login kecuali login/logout/endpoint perangkat; operator tidak boleh mengubah data selain scan; traceback disembunyikan; `/` dimatikan), `BUAHSAFE_LOG_LEVEL`, status perangkat live di `/api/devices`, model dimuat saat start (muat-pertama dari HDD 13,8 s membuat scan pertama melewati batas ack).
  - `database.py`: DB baru hanya berisi perangkat nyata BSF-001 (BSF-002/003 contoh dihapus dari seed).
  - `requirements.txt`: Flask, numpy 2.5.2, scipy 1.18.1, scikit-learn 1.9.0 (dikunci sesuai pickle model), joblib, gunicorn 26.2.0 (Linux).
  - Firmware `buahsafe_wifi/` (baru): WiFiManager (hotspot `BuahSafe-Setup`), HTTPS dengan root CA GTS/ISRG/SSL.com, long-poll, LCD status, watchdog 45 s. `config.h` rahasia diabaikan Git.
  - Server: agrocer dihentikan, diarsip ke `/srv/hdd1/archive/agrocer-20261023.tar.gz` (termasuk `sensor.db`) lalu dihapus; ingress `agrocermut` diganti `buahsafe-api.adsurkasur.my.id`; layanan `buahsafe.service` (gunicorn 1 worker, `MemoryMax=450M`, `ProtectSystem=strict`); kode, venv, dan DB di HDD; sandi akun seed diganti acak (`/etc/buahsafe/initial-credentials.txt`); cache npm/pip/go/apt dan snap nonaktif dibersihkan (flash 7,2 -> 8,9 GB bebas); journald dibatasi 200 MB.
  - Panduan `docs/DEPLOY_SERVER_WIFI.md`.
- **Files Modified**: `app.py`, `database.py`, `requirements.txt`, `wifi_device.py` (baru), `tests/test_wifi_production.py` (baru), `buahsafe_wifi/{buahsafe_wifi.ino,root_ca.h,config.example.h}` (baru), `docs/DEPLOY_SERVER_WIFI.md` (baru), `.gitignore`, `logs/*`.
- **Verification**: 68 unit test (termasuk 4 test WiFi/produksi), 9 auth, 6 E2E lulus; `python wifi_device.py` swa-uji OK. E2E lewat internet dengan ESP32 tiruan: kunci salah 401, alat offline 503 dengan pesan jelas, scan ANOMALI 71,7% dalam 3,25 s, ack `scan_no` sampai ke perangkat, operator ubah label 403, record uji dihapus. Di t530: inferensi 1,29 ms/scan, layanan 106 MB RAM, RAM tersedia 1,24 GB. Firmware belum diuji pada ESP32 fisik.

### [2026-10-23 15:55] [Antigravity]
- **Goal**: Implementasi mode perangkat ESP32 WiFi (long-poll & submit API) dan firmware Arduino WiFi untuk pemindai jarak jauh.
- **Actions**:
  - Mengembangkan `wifi_device.py` dengan antrean perintah long-poll dan penyerahan hasil scan aman.
  - Menambahkan endpoint `/api/device/poll` dan `/api/device/result` di `app.py` yang diproteksi kunci perangkat `X-Device-Key`.
  - Menambahkan firmware ESP32 WiFi di `buahsafe_wifi/` (`buahsafe_wifi.ino`, `config.example.h`, `root_ca.h`).
  - Menambahkan tes `tests/test_wifi_production.py` dan mengabaikan `buahsafe_wifi/config.h` di `.gitignore`.
- **Files**: `wifi_device.py`, `app.py`, `database.py`, `requirements.txt`, `.gitignore`, `buahsafe_wifi/`, `tests/test_wifi_production.py`, `logs/ACTIVITY_LOG.md`.
- **Verification**: 68 tests lulus (100% OK dalam 13.5s).

### [2026-10-23 00:25] [Claude Code]
- **Goal**: Audit kesiapan produksi backend sebagai pasangan `buahsafe-client` dan perbaikan temuan keamanan/integritas.
- **Actions**:
  - Menemukan bahwa `test_auth_production.py`, `test_sandbox_e2e.py`, dan `tests/test_server_api.py` menulis ke `data/buahsafe.db` (DB dataset nyata): 5 baris `JB-SANDBOX-01`, 4 akun uji, 31 token. Menambah override `BUAHSAFE_DB_PATH` di `database.py`; ketiga suite kini memakai DB sementara (`tests/__init__.py` + header tiap berkas root) dan `test_00_isolated_database` menjaga regresinya. Data yang telanjur tercemar **tidak** dihapus (menunggu keputusan pemilik).
  - `/api/scan`: kegagalan inferensi ML tidak lagi dipalsukan menjadi `NORMAL` 50%. Spektrum tetap disimpan tanpa prediksi, respons 503 mengarahkan pemeriksaan manual. `predictor.predict` tidak lagi memakai heuristik tebakan 730/680 bila model tidak ada (folder `models/` belum ter-commit, jadi clone baru akan diam-diam memakai tebakan).
  - CORS `*` diganti allowlist `BUAHSAFE_CORS_ORIGINS` (bawaan `http://localhost:5173,http://127.0.0.1:5173`).
  - Token di query string (`?token=`) dihapus karena ikut tercatat di feed `/api/debug` yang tanpa otentikasi.
  - `get_analytics_summary`: satu putusan per baris (prediksi lebih dulu, label sebagai cadangan) dan tingkat kelolosan dihitung dari baris berputusan saja (sebelumnya 0,0% karena baris akuisisi dataset ikut jadi penyebut).
- **Files Modified**: `app.py`, `database.py`, `predictor.py`, `tests/__init__.py`, `tests/test_app.py`, `tests/test_server_api.py`, `test_auth_production.py`, `test_sandbox_e2e.py`, `logs/*`.
- **Verification**: `run_local_sandbox.py --test` lolos 4/4: 64 unit test, 9 auth test, 6 E2E, build frontend. Jumlah baris `data/buahsafe.db` tetap 77 sebelum dan sesudah suite. Uji peramban 4 persona dijalankan terhadap salinan DB di scratchpad.

### [2026-10-22 17:00] [Antigravity]
- **Goal**: Implementasi otentikasi siap produksi (PBKDF2-HMAC-SHA256, token sesi Bearer 24 jam di SQLite, perlindungan rute berbasis peran / RBAC, dan manajemen pengguna oleh Owner) serta pembaruan seluruh suite pengujian.
- **Actions**:
  - Mengembangkan helper kriptografi `hash_password` (PBKDF2-HMAC-SHA256, 100.000 iterasi, salt 16-byte unik) dan `verify_password`.
  - Memperluas skema SQLite secara non-destruktif dengan tabel `auth_tokens` dan kolom pengguna (`password_hash`, `salt`, `is_active`, `last_login`).
  - Menulis decorator otorisasi `@require_auth(allowed_roles)` di `app.py` untuk memvalidasi token Bearer dan membatasi akses peran (Operator, Supervisor, Owner).
  - Menyediakan endpoint manajemen pengguna untuk Owner (`GET /api/users`, `POST /api/users`, `PUT /api/users/<id>/password`, `DELETE /api/users/<id>`) dengan proteksi anti-hapus-diri-sendiri.
  - Melindungi rute sensitif: scan sortasi, manajemen data mitra petani, serta penghapusan data pengukuran.
  - Membangun berkas pengujian keamanan otentikasi `test_auth_production.py` (8 pengujian: hashing, login sah, penolakan password salah, penolakan token fiktif, RBAC operator vs owner, siklus akun pengguna, pencabutan token logout).
  - Memperbarui unit test `tests/test_app.py`, `tests/test_server_api.py`, dan `test_sandbox_e2e.py` agar menyertakan token otorisasi yang sah.
  - Menghubungkan pengujian otentikasi ke orkestrator satu perintah `run_local_sandbox.py --test`.
- **Files Modified**: `database.py`, `app.py`, `test_auth_production.py` (baru), `tests/test_app.py`, `tests/test_server_api.py`, `test_sandbox_e2e.py`, `run_local_sandbox.py`, `logs/ACTIVITY_LOG.md`, `logs/DECISION_LOG.md`, `logs/CHANGELOG.md`.
- **Verification**: Seluruh 4 tahapan pengujian otomatis di `run_local_sandbox.py --test` lolos 100% (62 Backend Unit Tests, 8 Production Auth Security Tests, 6 Sandbox E2E Tests, dan Frontend Production Build).

### [2026-10-22 09:40] [Antigravity]
- **Goal**: Otomasi pengujian local-first sandbox suite (E2E) dan validasi menyeluruh tanpa dependensi hardware fisik.
- **Actions**:
  - Mengembangkan berkas pengujian terisolasi `test_sandbox_e2e.py` yang mencakup 6 skenario kritis:
    1. Health check & CORS preflight untuk kesiapan client Vercel.
    2. Autentikasi multi-peran (Operator, Supervisor, Owner) dan penolakan kredensial tidak valid.
    3. Inferensi akurasi model Machine Learning SVM (RBF) 6-kanal pada sampel normal vs. anomali.
    4. Pemantauan armada perangkat dan alur persistensi scan.
    5. Agregasi metrik analitik (pass rate, tren harian 14 hari).
    6. Siklus hidup CRUD Data Master Petani Mitra.
  - Memperbaiki penanganan encoding keluaran terminal Windows agar ramah cross-platform (CP1252/UTF-8).
- **Files Modified**: `test_sandbox_e2e.py` (baru), `logs/ACTIVITY_LOG.md`, `logs/CHANGELOG.md`.
- **Verification**: Seluruh 6 pengujian otomatis sandbox lolos (100% OK dalam 2.31s); 62 unit test bawaan lolos (100% OK dalam 3.12s).

### [2026-10-22 09:35] [Antigravity]
- **Goal**: Finalisasi backend server minimal dengan inferensi ML real-time, CORS untuk frontend Vercel, dan manajemen multi-peran (Operator, Supervisor, Owner).
- **Actions**:
  - Mengekspor model produksi SVM (RBF) 6-kanal kunci (`610, 680, 730, 760, 810, 860 nm`) ke `models/buahsafe_model_svm_6ch.joblib` (akurasi 78.0%, ROC-AUC 81.8%).
  - Membuat modul `predictor.py` untuk inferensi spektral real-time dengan probabilitas keyakinan (*confidence score*).
  - Memperluas skema `database.py` secara non-destruktif: migrasi kolom `prediction`, `confidence`, `device_id`, `operator_id` pada tabel `measurements`, serta inisialisasi tabel `users`, `devices`, dan `petani_mitra`.
  - Mengintegrasikan CORS native dan endpoint `/api/auth/login`, `/api/predict`, `/api/devices`, `/api/analytics`, dan `/api/master-data/petani` ke `app.py`.
  - Memperbaiki unit test CSV di `tests/test_app.py` dan menambahkan `tests/test_server_api.py`.
- **Files Modified**: `export_model.py` (baru), `models/buahsafe_model_svm_6ch.joblib` (baru), `predictor.py` (baru), `database.py`, `app.py`, `tests/test_app.py`, `tests/test_server_api.py` (baru).
- **Verification**: Seluruh 62 unit test lolos (`Ran 62 tests in 4.058s - OK`).

### [2026-09-25 07:41] [Antigravity]
- **Goal**: Track Arduino IDE standard sketch directory `buahsafe/buahsafe.ino` alongside root sketch.
- **Actions**: Added `buahsafe/buahsafe.ino` for direct Arduino IDE compatibility while preserving root `buahsafe.ino`.
- **Files Modified**: `buahsafe/buahsafe.ino`, `logs/ACTIVITY_LOG.md`.
- **Verification**: Files verified byte-identical, tracked in Git.

### [2026-09-19 05:30] [Claude Code]
- **Goal**: Perbaiki ID/label dataset pengujian (AMAN/BOSOK) dan jalankan ulang analisis Monev 3 di dataset final.
- **Actions**: Gabung batch 29/08 (310) + batch 3/09 dari `output/finalised/` (208); pindahkan 2 scan rotasi "a" yang lupa ganti ID (20:28:03 AMAN_19->AMAN_20, 20:31:25 AMAN_20->AMAN_21); `sehat`->`normal`; ID diseragamkan 3 digit; `scan_no` dinomori ulang 1-518 urut timestamp; kolom kosong `rotasi_sensor` dibuang. AMAN_010 tetap 6 scan (scan no. 80 terhapus di DB mentah, g-h tidak pernah di-scan ulang). `eda.py`, `compare_models.py`, `compare_datasets_model.py`, `tune_and_importance.py` diarahkan ke dataset final lalu dijalankan ulang.
- **Files Modified**: `output/finalised/finalise_dataset.py` (baru), `output/finalised/buahsafe_dataset_gabungan_final.{csv,xlsx}` (baru), `output/data_analysis/*.py`, `output/data_analysis/eda_buahsafe_output/*`, `output/data_analysis/model_comparison_output/*`.
- **Verification**: Validasi di `finalise_dataset.py` lolos (518 baris, 65 objek, 270/248, tiap ID rotasi a-h kecuali AMAN_010, tanpa rotasi ganda, ID kontigu dalam waktu). EDA identik dengan versi lama; hasil model bergeser kecil (SVM tuned Acc 79,2->77,9, F1 76,6->74,4, AUC 84,3->82,4), urutan SVM > RF > LR tetap.

### [2026-09-16 17:25] [Antigravity]
- **Goal**: Initialize modular logging system and mandatory agent protocols.
- **Actions**: Created `logs/` directory and established `AGENTS.md`.
- **Files Modified**: `AGENTS.md`, `logs/README.md`, `logs/ACTIVITY_LOG.md`, `logs/DECISION_LOG.md`, `logs/CHANGELOG.md`.
- **Verification**: Git status verified.\n