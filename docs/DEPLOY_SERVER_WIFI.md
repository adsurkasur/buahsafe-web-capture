# Server produksi + ESP32 conveyor (WiFi)

Status per 2026-10-23: server berjalan di HP t530 Thin Client (`adsur@192.168.1.10`) dan bisa diakses publik di `https://buahsafe-api.adsurkasur.my.id` (URL sementara). Alur scan sudah diuji lewat internet memakai ESP32 tiruan (spektrum asli dari dataset final). Belum diuji dengan ESP32 fisik.

## Arsitektur

```text
Mitra                                   Server (HP t530)
Belt conveyor -> PIR -> ESP32 + AS7265x --WiFi/HTTPS--> Cloudflare Tunnel --> gunicorn 127.0.0.1:5000 --> SVM 18 kanal
  detak  GET  /api/device/poll (tiap 10 dtk)                                    |
  hasil  POST /api/device/auto-scan (tiap buah)                                 +--> SQLite (HDD)
Antrean web operator di ujung belt (Vercel) --HTTPS--> /api/measurements (tiap 1 dtk)
```

Mode `BUAHSAFE_DEVICE_MODE=conveyor` (produksi). Belt berjalan terus dan motornya bersaklar sendiri. Sensor PIR memicu ESP32: lampu halogen menyala, AS7265x mengukur sekali saat buah lewat, lalu ESP32 mengirim baris `DATA,...` (format sama dengan protokol USB) ke `/api/device/auto-scan`. Server memberi ID `CV-YYYYMMDD-NNNN`, menilai dengan model, dan menjawab nomor urut + putusan untuk LCD dan buzzer. Buah yang gagal diukur tetap dilaporkan (`{"error": ...}`) dan mendapat nomor, agar urutan antrean tidak bergeser; barisnya bertanda `GAGAL` dan tidak ikut ekspor dataset. `/api/scan` manual menjawab 409 di mode ini.

Mode `wifi` (scan diperintah dari web lewat long-poll) masih ada di `wifi_device.py` untuk akuisisi dengan buah diam. Mode USB lama (`serial`, bawaan) tetap dipakai untuk akuisisi dataset di laptop.

Mode USB lama (`BUAHSAFE_DEVICE_MODE=serial`, bawaan) tetap dipakai untuk akuisisi dataset di laptop.

## Tata letak server

| Lokasi | Isi |
|---|---|
| `/srv/hdd1/buahsafe/app` | Kode backend |
| `/srv/hdd1/buahsafe/venv` | Python 3.14 venv (289 MB, di HDD agar flash tidak penuh) |
| `/srv/hdd1/buahsafe/data/buahsafe.db` | Database produksi |
| `/etc/buahsafe/buahsafe.env` | Konfigurasi dan kunci perangkat (`root:adsur 640`) |
| `/etc/buahsafe/initial-credentials.txt` | Sandi awal acak akun `owner`, `supervisor`, `operator` (`root 600`) |
| `/etc/systemd/system/buahsafe.service` | gunicorn 1 worker, 8 thread, `MemoryMax=450M` |
| `/etc/cloudflared/config.yml` | `buahsafe-api.adsurkasur.my.id -> http://localhost:5000` |

Server **wajib 1 worker**: antrean scan ESP32 tersimpan di memori proses. Jangan menaikkan `--workers`.

Perintah harian:

```bash
sudo systemctl status buahsafe
journalctl -u buahsafe -f
sudo cat /etc/buahsafe/initial-credentials.txt
```

Setelah login pertama, ganti ketiga sandi lewat Data Master lalu hapus `initial-credentials.txt`.

### Memperbarui kode

```bash
cd /srv/hdd1/buahsafe/app && git pull
/srv/hdd1/buahsafe/venv/bin/pip install --no-cache-dir -r requirements.txt
sudo systemctl restart buahsafe
```

Versi scikit-learn dikunci di 1.9.0 karena `models/buahsafe_model_svm_6ch.joblib` dipickle dengan versi itu. Jika model dilatih ulang dengan versi lain, naikkan pin di `requirements.txt` bersamaan.

### Variabel lingkungan

| Variabel | Nilai produksi | Fungsi |
|---|---|---|
| `BUAHSAFE_ENV` | `production` | Semua API wajib login, traceback tidak dikirim ke klien, dasbor USB `/` dimatikan |
| `BUAHSAFE_DEVICE_MODE` | `conveyor` | Alat dipicu PIR dan mengirim hasil sendiri (`wifi` = scan diperintah dari web) |
| `BUAHSAFE_DEVICE_ID` | `BSF-001` | Harus sama dengan firmware |
| `BUAHSAFE_DEVICE_KEY` | acak 43 karakter | Harus sama dengan `config.h` firmware |
| `BUAHSAFE_DB_PATH` | `/srv/hdd1/buahsafe/data/buahsafe.db` | Database di HDD |
| `BUAHSAFE_CORS_ORIGINS` | `http://localhost:5173,...` | **Tambahkan domain Vercel klien** |
| `BUAHSAFE_LOG_LEVEL` | `INFO` | Kurangi tulisan log ke flash |

Klien Vercel: set `VITE_API_URL=https://buahsafe-api.adsurkasur.my.id`, lalu tambahkan domain Vercel ke `BUAHSAFE_CORS_ORIGINS` dan restart `buahsafe`.

## Firmware ESP32 (`buahsafe_wifi/`)

Board: ESP32-WROOM-32 DevKit USB-C dengan chip USB CP2102. Skema, tabel koneksi, catatan catu daya, dan urutan uji rakit: [PANDUAN_RANGKAIAN_ALAT.md](PANDUAN_RANGKAIAN_ALAT.md). Wiring mengikuti Tabel Koneksi di draf laporan: PIR HC-SR501 OUT GPIO 27, relay lampu GPIO 4, buzzer GPIO 25, LCD SDA 13/SCL 14, AS7265x SDA 21/SCL 22. Pin dan polaritas bisa ditimpa di `config.h` (lihat `config.example.h`).

1. Pasang driver CP210x (Silicon Labs) bila port COM tidak muncul.
2. Arduino IDE: tambahkan board manager `https://espressif.github.io/arduino-esp32/package_esp32_index.json`, pasang **esp32 by Espressif** (diuji 3.3.12), pilih **ESP32 Dev Module**.
3. Library: *SparkFun Spectral Triad AS7265X*, *LiquidCrystal I2C*, *WiFiManager* (tzapu).
4. `config.h` berisi URL server, kunci perangkat, dan sandi hotspot setup. Berkas ini sengaja tidak masuk Git; salin dari `config.example.h` bila belum ada. Kunci harus sama dengan `BUAHSAFE_DEVICE_KEY` di server.
5. Upload. Program memakai 89% partisi aplikasi bawaan (1,17 MB); bila fitur bertambah, pilih *Partition Scheme: Huge APP (3MB No OTA)*. Atau dengan CLI:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 buahsafe_wifi
arduino-cli upload --fqbn esp32:esp32:esp32 -p COM5 buahsafe_wifi
```

### Pemasangan di mitra

1. Nyalakan alat. Bila belum kenal WiFi, LCD menampilkan `Setup WiFi HP ke / BuahSafe-Setup`.
2. Dari HP, sambungkan ke WiFi `BuahSafe-Setup` (sandi dari `config.h`), halaman setup terbuka otomatis. Pilih WiFi mitra dan isi sandinya.
3. LCD `BuahSafe siap / Jalankan belt` berarti alat sudah terhubung ke server. Di web, menu Antrean Conveyor menampilkan "Alat terhubung". Tunggu 30–60 detik setelah alat menyala sebelum belt dijalankan: PIR HC-SR501 perlu menstabilkan diri.
4. Pindah WiFi: tahan tombol BOOT sambil menyalakan alat selama 3 detik.

### Arti pesan LCD

| LCD | Arti | Tindakan |
|---|---|---|
| `WiFi terputus` | Sinyal WiFi hilang | Alat menyambung ulang sendiri |
| `Server tdk jawab / Server: -1` | Tidak ada internet atau galat TLS | Periksa internet mitra |
| `Server tdk jawab / Server: 502` | Tunnel jalan, backend mati | `sudo systemctl restart buahsafe` |
| `Kunci alat salah` | `config.h` tidak sama dengan server | Samakan `BUAHSAFE_DEVICE_KEY` |
| `#57 NORMAL / Yakin 84%` (1 bip) | Buah ke-57 normal | Masukkan ke keranjang normal |
| `#57 ANOMALI / Yakin 91%` (3 bip panjang) | Buah ke-57 terindikasi rusak | Masukkan ke keranjang anomali |
| `Alat diputus / oleh pemilik` | Pemilik memutus alat di web | Sambungkan lagi di Pengaturan > Perangkat |
| `#57 GAGAL / Sisihkan buah` (2 bip berulang) | Sensor gagal, buah lewat saat alat sibuk, atau model gagal | Sisihkan untuk diperiksa manual |
| `GAGAL KIRIM -1 / Sisihkan buah` | Server tak terjangkau; buah tidak bernomor | Sisihkan buah; hentikan belt sampai internet pulih |
| `ERROR AS7265x` | Sensor tidak terbaca | Periksa kabel I2C sensor |

### Kalibrasi di lokasi

Semua kenop ada di `config.h` (daftar lengkap dan nilai bawaan di `config.example.h`). Setelah mengubah kenop, flash ulang. Setelan yang aktif tercetak di Serial Monitor 115200 (baris `CFG,...`) dan ikut tercatat di log server tiap buah (`jeda lampu`, `sampel`, `mode lampu`), jadi hasil antarsetelan bisa dibandingkan:

```bash
ssh adsur@192.168.1.10 'journalctl -u buahsafe --since today | grep CONVEYOR'
```

**Langkah 0, jeda lampu (paling penting).** Data latih diambil dengan lampu dipanaskan 3000 ms sebelum mengukur. Bila conveyor mengukur saat lampu belum terang penuh, intensitas lebih rendah daripada data latih dan putusan model bergeser. Cara memeriksa:

1. Letakkan satu buah diam di depan sensor, lalu buka Serial Monitor.
2. Flash dengan `LAMP_SETTLE_MS 3000`, picu PIR dengan tangan 3 kali, lalu catat baris `DATA` (kolom 730 dan 810 nm adalah nilai ke-13 dan ke-15 setelah nomor).
3. Ulangi dengan `LAMP_SETTLE_MS 300`.
4. Bila nilai 300 ms masih di atas sekitar 95% nilai 3000 ms, jeda 300 ms aman. Bila lebih rendah, naikkan `LAMP_SETTLE_MS` selama waktu lintas buah masih cukup (langkah 3 di bawah), atau pakai `LAMP_MODE 1` (lampu menyala terus selama alat siap, tanpa jeda). Dengan `LAMP_MODE 1`, periksa panas lampu terhadap buah dan rangka.

`MEASURE_SAMPLES` (bawaan 1) merata-ratakan beberapa pengukuran per buah. Nilai ini hanya berguna bila buah cukup lama di depan sensor, karena tiap sampel menambah sekitar 0,4 detik. `SENSOR_GAIN` dan `SENSOR_INTEGRATION_CYCLES` harus sama dengan firmware akuisisi dataset; mengubahnya berarti data latih harus diambil ulang.

1. **Polaritas relay.** Bila lampu menyala terus saat alat diam, ubah `RELAY_ACTIVE_LOW` di `config.h`.
2. **PIR pada jambu.** Lewatkan 20 buah satu per satu dan pastikan nomor di LCD bertambah 20. Bila ada yang terlewat atau satu buah memicu dua kali, ganti ke sensor halangan IR (`TRIGGER_ACTIVE_LEVEL LOW` untuk E18-D80NK) atau atur `TRIGGER_COOLDOWN_MS`.
3. **Waktu lewat.** Server mencatat lama sinyal PIR aktif dan lama pengukuran tiap buah: `journalctl -u buahsafe | grep CONVEYOR` atau status perangkat di `/api/status` (`last_trigger_ms`, `last_measure_ms`). `LAMP_SETTLE_MS` + waktu ukur (~0,5 dtk) harus lebih kecil dari waktu buah berada di depan sensor. Bila belt terlalu cepat, perlambat belt atau beri jarak antarbuah.
4. **Jarak antarbuah.** Buah berikutnya sebaiknya baru memicu setelah hasil buah sebelumnya kembali (~1 dtk). Picu yang terlalu cepat dilaporkan `GAGAL` (`TERLAMBAT_UKUR`), bukan diukur terlambat.

Sertifikat: firmware mempercayai root CA Google Trust Services, Let's Encrypt (ISRG), dan SSL.com (`root_ca.h`). Root paling awal kedaluwarsa 2035-06-04.

## ESP32 virtual, model, dan backup (2026-10-25)

- `buahsafe-sim.service` menjalankan `esp32_simulator.py` (firmware `sim-2.0-conveyor`): detak tiap 10 detik, dan hanya mengirim buah bila supervisor/owner menekan "Jalankan simulasi conveyor (10 buah)" di web (`POST /api/device/simulate`). Spektrum = scan nyata dari 13 buah uji independen (`ml/holdout_fruits.json`), jarak antarbuah 3–6 detik, buah ke-7 dibuat gagal. ID berawalan `SIM-`. Perangkat tampil sebagai "Meja Sortasi (Simulator)" lewat `BUAHSAFE_DEVICE_LABEL`.
- Model: `models/buahsafe_model.joblib` dibuat oleh `ml/evaluate_models.py` (SVM-RBF 18 kanal, ambang anomali 0,45, dilatih 80% buah). Bahan laporan: `ml/report_materials.py` -> `../laporan-akhir/bahan-laporan-ml/`.
- `buahsafe-backup.timer` (02.00) menjalankan `deploy/backup_db.py` ke `/srv/hdd1/backups/buahsafe`, simpan 14 hari, dicek `integrity_check`.
- Berkas unit ada di `deploy/`; pasang dengan `sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/ && sudo systemctl daemon-reload`.

Saat ESP32 asli dipasang di mitra:

```bash
sudo systemctl disable --now buahsafe-sim
sudo sed -i 's/^BUAHSAFE_DEVICE_LABEL=.*/BUAHSAFE_DEVICE_LABEL=Meja Sortasi A/' /etc/buahsafe/buahsafe.env
cd /srv/hdd1/buahsafe/app && ../venv/bin/python ml/evaluate_models.py --full && sudo systemctl restart buahsafe
```
