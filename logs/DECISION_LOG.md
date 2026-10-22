# Decision Log (Architecture Decision Records)

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
