# BuahSafe Web Capture

> Untuk operasi perangkat, pemeliharaan kode, dan pembekuan versi HAKI, baca [`docs/OPERATOR_AND_MAINTAINER_GUIDE.md`](docs/OPERATOR_AND_MAINTAINER_GUIDE.md) dan [`docs/HAKI_RELEASE_CHECKLIST.md`](docs/HAKI_RELEASE_CHECKLIST.md).

Dashboard Flask lokal untuk mengambil dataset mentah 18 kanal AS7265x melalui
ESP32. Setiap klik menghasilkan satu pembacaan dan satu record SQLite.

Firmware memakai dua bus I2C: LCD pada SDA GPIO13/SCL GPIO14 dan sensor Triad AS7265x
pada SDA GPIO21/SCL GPIO22. Semua perangkat tetap harus berbagi GND yang sama.

## 18 Kanal AS7265x

Triad AS7265x menggabungkan 3 sensor optik:
- **AS72651** (UV-VIS): 410, 435, 460, 485, 510, 535 nm
- **AS72652** (VIS): 560, 585, 610, 645, 680, 705 nm
- **AS72653** (NIR): 730, 760, 810, 860, 900, 940 nm

## Persiapan pertama

1. Upload `buahsafe.ino` ke ESP32.
2. Tutup Arduino Serial Monitor.
3. Virtual environment `.venv` sudah disiapkan di folder ini. Jika perlu dibuat
   ulang, jalankan:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

## Menjalankan

Klik dua kali `run_buahsafe.bat`, atau jalankan:

```powershell
.\.venv\Scripts\python.exe launch.py
```

Buka `http://127.0.0.1:5000`, pilih port COM, lalu hubungkan ESP32. Masukkan ID
jambu dan tekan **Ambil satu scan**.

## Penyimpanan

Database berada di `data/buahsafe.db`. Tombol **Unduh CSV** menghasilkan dataset
18 kanal yang bisa dibuka di Excel / Python. Jangan menghapus database saat aplikasi berjalan.

## Catatan dataset

- Gunakan ID berbeda untuk setiap jambu fisik.
- Ambil beberapa scan dari posisi/sisi berbeda untuk tiap jambu.
- Jaga pencahayaan halogen, jarak sensor, dan posisi buah konsisten.
- Saat membagi train/test, kelompokkan berdasarkan `fruit_id` agar scan jambu yang
  sama tidak bocor ke kedua set.
