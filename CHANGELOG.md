# Changelog

Semua perubahan penting pada proyek ini dicatat di file ini.

Format mengikuti [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
dan proyek ini mengikuti [Semantic Versioning](https://semver.org/lang/id/)
(`MAJOR.MINOR.PATCH`).

## [1.1.0] - 2026-08-19

### Added
- Kolom pengukuran fisik manual per baris data di Riwayat Pengukuran: `Diameter (cm)`, `Rotasi` (A/B/C/D), dan `Elevasi (cm)` (jarak titik sensor dari alas). Semua kolom bersifat opsional dan diisi/diubah langsung dari tabel, tersimpan lewat endpoint `PATCH /api/measurements/<id>/diameter`, `/rotasi`, dan `/elevasi`. Ikut disertakan di ekspor CSV.
- Migrasi skema database otomatis dan idempoten (`ALTER TABLE ADD COLUMN`) untuk `diameter_cm`, `rotasi`, `elevasi_cm` -- aman dijalankan di database lama tanpa mengubah data spektral/label yang sudah ada.

## [1.0.2] - 2026-08-17

### Removed
- Menghapus tombol `⚡ Debug Log` (`quickDebugBtn`) dari *header* antarmuka utama untuk mengurangi redundansi. Akses ke Debug Console tetap dipertahankan melalui tombol "Buka Debug Console" pada *Error Inspector* saat terjadi kegagalan dan tombol navigasi lainnya.

## [1.0.1] - 2026-08-17

### Fixed
- Nama proyek/repositori dikoreksi dari `buahsafe-data-collector` menjadi
  `buahsafe-web-capture` agar konsisten dengan nama produk yang sudah
  dipakai di dokumen spesifikasi dan dokumentasi lain
  (`BuahSafe Web Capture`). Perubahan `1.0.0` sebelumnya sempat memakai
  nama yang tidak konsisten.

## [1.0.0] - 2026-08-17

Rilis pertama yang diberi tag versi resmi. Menandai titik saat aplikasi
akuisisi data (single-operator, ESP32 + AS7265x 18-kanal) sudah stabil,
teruji (54/54 automated test, plus pengujian hardware end-to-end), dan
didokumentasikan secara lengkap.

### Added
- Aplikasi web lokal (Flask) untuk mengendalikan ESP32 dan mengambil
  pembacaan spektral 18-kanal dari sensor AS7265x.
- Retry otomatis (server hingga 3x, browser 1x tambahan) saat kegagalan
  sementara pada koneksi/pemindaian.
- Validasi ketat setiap pembacaan (20 kolom, seluruh nilai harus *finite*)
  sebelum disimpan ke SQLite.
- Riwayat pengukuran dengan pencarian, filter label, hapus baris
  tunggal/terpilih/reset total, dan ekspor dataset ke CSV.
- Debug Console real-time (log Error/Serial TX-RX/Parser/Device).
- Panduan validasi & pesan bantu langsung di antarmuka untuk setiap langkah
  alur kerja (pilih port, hubungkan perangkat, isi ID jambu, pindai),
  diselaraskan dengan diagram alur kerja yang disusun tim.
- Tombol "Coba lagi" pada error inspector kini kontekstual -- mengulang
  aksi yang sebenarnya gagal (koneksi vs. pemindaian), bukan selalu
  mengulang pemindaian.
- Nomor versi aplikasi (`_version.py`) yang disurfacekan lewat `/api/status`,
  `/api/debug`, dan panel Debug Console.

### Changed
- Nama proyek/repositori berubah dari `buahsafe-internal` menjadi
  `buahsafe-data-collector` agar lebih mencerminkan fungsinya.
- Vocabulary label hasil diganti dari `bagus`/`rusak` menjadi
  `normal`/`anomali` di database, API, dan antarmuka. Data lama dimigrasikan
  otomatis dan idempotent saat aplikasi dijalankan (`database.initialize()`).
- README ditulis ulang menjadi dokumentasi proyek yang lengkap (fitur, alur
  kerja, instalasi, skema data, testing).

### Documentation
- Menambahkan diagram alur kerja pemindaian (`docs/assets/flowchart-scan-workflow.png`)
  yang mencerminkan alur yang sudah diimplementasikan di versi ini.
- Menambahkan diagram visi/roadmap multi-role (operator/supervisor/owner,
  manajemen armada perangkat, dashboard analitik) di
  `docs/assets/flowchart-roadmap-role-based.png` sebagai referensi arah
  pengembangan -- **belum diimplementasikan** pada versi ini (lihat README
  bagian Roadmap).

[1.0.2]: https://github.com/adsurkasur/buahsafe-web-capture/releases/tag/v1.0.2
[1.0.1]: https://github.com/adsurkasur/buahsafe-web-capture/releases/tag/v1.0.1
[1.0.0]: https://github.com/adsurkasur/buahsafe-web-capture/releases/tag/v1.0.0
