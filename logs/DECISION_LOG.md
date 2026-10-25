# Decision Log (Architecture Decision Records)

### [DEC-008] Mode Conveyor: Alat Memicu Scan Sendiri, Server Memberi Nomor Urut
- **Date**: 2026-10-25
- **Status**: Accepted (menggantikan alur scan-diperintah-web pada DEC-006 untuk produksi)
- **Context**: Alat sebenarnya adalah belt conveyor yang berjalan terus dengan pemicu PIR; tidak ada operator yang menekan tombol per buah, dan operator di ujung belt mencocokkan hasil dengan buah berdasarkan urutan.
- **Decision**: ESP32 mengukur saat PIR terpicu dan mengirim ke `/api/device/auto-scan`; server memberi nomor urut harian yang tampil di LCD, buzzer, dan antrean web. Setiap picu dilaporkan, termasuk yang gagal, supaya urutan tidak bergeser. Long-poll diganti detak karena memblokir ESP32 sampai 10 detik.
- **Alternatives**: Antrean ulang di ESP32 saat gagal kirim (ditolak: urutan bisa bergeser dan hasil terlambat untuk buah yang sudah lewat); pemilahan otomatis dengan aktuator (belum ada di alat).
- **Consequences**: Satu scan per buah, sehingga recall per scan (0,625 di holdout) yang berlaku; ambang menjadi keputusan bisnis. Model dilatih dari buah diam; kinerja pada buah bergerak perlu data conveyor berlabel. Bila internet putus, buah tidak bernomor dan harus disisihkan.

### [DEC-007] Model 18 Kanal Dipilih Lewat Nested CV + Holdout, Ambang Berbasis Recall
- **Date**: 2026-10-25
- **Status**: Accepted (menggantikan pilihan SVM 6 kanal C=100 pada DEC-003)
- **Context**: Model 6 kanal dipilih tanpa perbandingan setara dengan 18 kanal, dan tuning lama memakai fold yang sama dengan evaluasi. Di meja sortasi, buah busuk yang lolos lebih mahal daripada alarm palsu.
- **Decision**: 13 buah disisihkan sebagai holdout; enam kandidat (LR/SVM/RF x 6/18 kanal) dinilai dengan validasi silang bersarang per buah; pilih F1 tertinggi; ambang anomali = ambang tertinggi dengan recall out-of-fold >= 0,80. Model demo dilatih 80% buah agar ESP32 virtual memutar buah yang tidak pernah dilihat model; dilatih ulang 100% (`--full`) saat alat asli dipasang. Kanal dan ambang disimpan di artefak, bukan di kode.
- **Alternatives**: Tetap SVM 6 kanal (F1 0,769, selisih di dalam simpangan baku; tetap layak); memilih menurut akurasi atau AUC saja (mengabaikan biaya buah busuk lolos).
- **Consequences**: Recall per scan di holdout 0,625, di bawah target; perataan beberapa sisi per buah (12/13 benar) menjadi saran utama. Inferensi 16 ms/scan di t530 (lebih berat dari 1,3 ms model lama, tetap jauh di bawah pemanasan lampu 3 s).

### [DEC-006] ESP32 WiFi dengan Long-Poll HTTPS ke Server Terpisah
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: Alat sortasi dipasang di mitra, server ML di HP t530 pemilik. Protokol USB serial tidak bisa menjangkau server jarak jauh, dan ESP32 di balik NAT mitra tidak bisa dihubungi dari luar.
- **Decision**: ESP32 melakukan long-poll HTTPS (`/api/device/poll`, tunggu maksimal 10 s) lewat Cloudflare Tunnel yang sudah ada, lalu mengirim baris `DATA,...` yang sama dengan protokol serial ke `/api/device/result`. Server menyimpan antrean satu scan di memori proses (wajib 1 worker gunicorn). Perangkat diautentikasi dengan kunci bersama `X-Device-Key`. WiFi mitra diatur lewat portal WiFiManager tanpa flashing ulang.
- **Alternatives**: MQTT broker (komponen tambahan dan RAM di server yang sudah padat); WebSocket (tidak perlu untuk satu perintah per beberapa detik); jembatan USB di mitra (perangkat tambahan per mitra); polling pendek tiap 1 s (handshake dan trafik berlebih).
- **Consequences**: Satu set perangkat didukung. Banyak perangkat memerlukan antrean per `device_id` dan kunci per perangkat. Mode USB tetap tersedia untuk akuisisi dataset.

### [DEC-005] Gagal-Aman pada Putusan Sortasi, Isolasi DB Uji, dan CORS Allowlist
- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**: Audit produksi menemukan tiga jalur yang membuat keluaran sistem tidak dapat dipercaya: (1) inferensi gagal → `NORMAL` 50% (buah masuk keranjang hijau tanpa dinilai), model hilang → heuristik tebakan; (2) suite uji menulis ke DB dataset nyata; (3) CORS `*` sementara endpoint label/koneksi/ekspor tidak memerlukan token, sehingga situs lain yang dibuka di peramban operator bisa membaca dan mengubah data lokal.
- **Decision**: Tanpa model yang sah tidak ada putusan (HTTP 503 + arahan pemeriksaan manual, spektrum tetap disimpan). DB dapat dialihkan lewat `BUAHSAFE_DB_PATH` dan semua suite memakainya. CORS hanya untuk origin di `BUAHSAFE_CORS_ORIGINS`.
- **Alternatives**: Mewajibkan token di semua endpoint baca/label. Ditunda karena dasbor akuisisi lokal (`templates/index.html`) memakai endpoint itu tanpa login; perlu keputusan apakah dasbor lama ikut login.
- **Affected**: `app.py`, `predictor.py`, `database.py`, seluruh suite uji. Deploy Vercel wajib mengisi `BUAHSAFE_CORS_ORIGINS` dengan domain klien.

### [DEC-004] Production-Ready Local Authentication & RBAC via Salted PBKDF2 and 24-Hour Bearer Session Tokens
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Sistem bertransformasi dari prototype ke sistem siap produksi. Pilihan demo akun dihilangkan, kata sandi plain-text diganti hashing standar kriptografi industri, dan otentikasi rute berbasis peran (RBAC) diberlakukan.
- **Decision**:
  1. Hashing kata sandi menggunakan `hashlib.pbkdf2_hmac` dengan algoritma `sha256`, salt 16-byte acak per pengguna, dan 100.000 iterasi.
  2. Sesi login menerbitkan Bearer token 32-byte hex yang disimpan pada tabel SQLite `auth_tokens` dengan masa berlaku 24 jam dan fitur pencabutan (*revocation*) saat logout.
  3. Skema RBAC dengan hak akses tegas: Operator (scan), Supervisor (dashboard, history, export CSV, delete measurement), Owner (semua hak akses + manajemen akun pengguna & master data).
  4. Manajemen pengguna dikelola eksklusif oleh Owner melalui antarmuka Data Master (tidak ada pendaftaran publik mandiri).
- **Consequences**: Keamanan data mutu dan integritas pemindaian terlindungi dari tampering, sesi pengguna aman dan transparan, serta memenuhi standar audit kepatuhan gudang.

### [DEC-003] Server Minimal Terpisah: Dedicated ML Inference Core & CORS untuk Klien Web
- **Date**: 2026-10-22
- **Status**: Accepted
- **Context**: Klien antarmuka pengguna (`buahsafe-client`) dideploy secara terpisah (misal di Vercel atau static hosting), sementara server backend bertugas sebagai inti pemrosesan machine learning dan antarmuka serial perangkat keras.
- **Decision**: Menjadikan backend Flask sebagai server minimal yang mengekspos endpoint inferensi spektral (`/api/predict` dan `/api/scan`) dengan model SVM RBF 6-kanal, mendukung CORS penuh untuk peramban, serta menyediakan skema multi-peran (Operator, Supervisor, Owner) di SQLite tanpa bloat framework tambahan.
- **Consequences**: Antarmuka web dapat dideploy ke Vercel tanpa dependensi backend lokal, sementara server backend dapat berjalan ringan di PC sortasi atau gateway lokal.

### [DEC-002] Dataset final sebagai sumber tunggal analisis ML
- **Date**: 2026-09-19
- **Status**: Accepted
- **Context**: `fixed/buahsafe_dataset_gabungan_08092026_clean.*` masih berisi 2 scan dengan ID tertukar, format ID campuran, dan `scan_no` dobel (303-310).
- **Decision**: Semua skrip analisis membaca `output/finalised/buahsafe_dataset_gabungan_final.xlsx`, yang dibangun ulang dari data mentah oleh `output/finalised/finalise_dataset.py` (koreksi ID dikunci per timestamp, validasi ketat). File lama dibiarkan apa adanya sebagai arsip.
- **Consequences**: Angka Monev 3 di laporan perlu diperbarui (lihat PENJELASAN_ML_MONEV3.md §8.D). Batch baru cukup ditambahkan ke skrip finalisasi.

### [DEC-001] Adoption of Modular Logging Protocol
- **Date**: 2026-09-16
- **Status**: Accepted
- **Context**: Standardizing change tracking, observability, and auditability across all managed projects for AI agents and human contributors.
- **Decision**: Mandate `logs/ACTIVITY_LOG.md`, `logs/DECISION_LOG.md`, and `logs/CHANGELOG.md` updates across all repositories.
- **Consequences**: Consistent history, reduced context loss during multi-agent handoffs.
