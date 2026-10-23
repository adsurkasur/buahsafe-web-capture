# Server produksi + ESP32 WiFi

Status per 2026-10-23: server berjalan di HP t530 Thin Client (`adsur@192.168.1.10`) dan bisa diakses publik di `https://buahsafe-api.adsurkasur.my.id` (URL sementara). Alur scan sudah diuji lewat internet memakai ESP32 tiruan (spektrum asli dari dataset final). Belum diuji dengan ESP32 fisik.

## Arsitektur

```text
Mitra                                   Server (HP t530)
ESP32 + AS7265x --WiFi/HTTPS-->  Cloudflare Tunnel --> gunicorn 127.0.0.1:5000 --> SVM 6 kanal
  long-poll /api/device/poll                                  |
  POST /api/device/result                                     +--> SQLite (HDD)
Peramban operator (Vercel) --HTTPS--> /api/scan, /api/measurements, ...
```

ESP32 berada di balik NAT jaringan mitra, jadi server tidak bisa memanggilnya. ESP32 yang terus bertanya (long-poll maksimal 10 detik). Saat operator menekan scan, server memberi perintah ke ESP32 yang sedang menunggu, ESP32 memindai, lalu mengirim baris `DATA,...` yang formatnya sama dengan protokol USB. Implementasinya ada di `wifi_device.py`. Waktu satu scan: sekitar 3 detik jaringan dan server, ditambah 3 detik pemanasan lampu.

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
| `BUAHSAFE_DEVICE_MODE` | `wifi` | Pakai `WifiDevice` alih-alih port serial |
| `BUAHSAFE_DEVICE_ID` | `BSF-001` | Harus sama dengan firmware |
| `BUAHSAFE_DEVICE_KEY` | acak 43 karakter | Harus sama dengan `config.h` firmware |
| `BUAHSAFE_DB_PATH` | `/srv/hdd1/buahsafe/data/buahsafe.db` | Database di HDD |
| `BUAHSAFE_CORS_ORIGINS` | `http://localhost:5173,...` | **Tambahkan domain Vercel klien** |
| `BUAHSAFE_LOG_LEVEL` | `INFO` | Kurangi tulisan log ke flash |

Klien Vercel: set `VITE_API_URL=https://buahsafe-api.adsurkasur.my.id`, lalu tambahkan domain Vercel ke `BUAHSAFE_CORS_ORIGINS` dan restart `buahsafe`.

## Firmware ESP32 (`buahsafe_wifi/`)

Board: ESP32-WROOM-32 DevKit USB-C dengan chip USB CP2102. Wiring sama dengan firmware USB (LCD SDA 13/SCL 14, sensor SDA 21/SCL 22, relay 26 active-low, buzzer 25).

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
3. LCD `BuahSafe siap / Menunggu scan` berarti alat sudah terhubung ke server. Di web, perangkat BSF-001 berstatus Online.
4. Pindah WiFi: tahan tombol BOOT sambil menyalakan alat selama 3 detik.

### Arti pesan LCD

| LCD | Arti | Tindakan |
|---|---|---|
| `WiFi terputus` | Sinyal WiFi hilang | Alat menyambung ulang sendiri |
| `Server tdk jawab / Server: -1` | Tidak ada internet atau galat TLS | Periksa internet mitra |
| `Server tdk jawab / Server: 502` | Tunnel jalan, backend mati | `sudo systemctl restart buahsafe` |
| `Kunci alat salah` | `config.h` tidak sama dengan server | Samakan `BUAHSAFE_DEVICE_KEY` |
| `Belum terkonfirm` | Data terkirim, nomor scan belum kembali | Cek riwayat di web |
| `ERROR AS7265x` | Sensor tidak terbaca | Periksa kabel I2C sensor |

Sertifikat: firmware mempercayai root CA Google Trust Services, Let's Encrypt (ISRG), dan SSL.com (`root_ca.h`). Root paling awal kedaluwarsa 2035-06-04.
