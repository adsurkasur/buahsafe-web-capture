# Panduan rangkaian alat BuahSafe (conveyor)

Panduan merakit elektronik alat sortasi BuahSafe: ESP32, sensor AS7265x, PIR HC-SR501, relay lampu halogen, LCD 16x2 I2C, dan buzzer. Pin di sini sama dengan Tabel Koneksi di draf laporan dan dengan nilai bawaan firmware `buahsafe_wifi/` (2.2.0-conveyor). Bila pin diubah saat merakit, ubah juga di `config.h` (lihat `config.example.h`).

Cara flash firmware dan menyambungkan alat ke server ada di [DEPLOY_SERVER_WIFI.md](DEPLOY_SERVER_WIFI.md).

## 1. Daftar komponen

| No | Komponen | Keterangan |
|---|---|---|
| 1 | ESP32-WROOM-32 DevKit (USB-C, CP2102) | Board "ESP32 Dev Module" di Arduino IDE |
| 2 | SparkFun Triad Spectroscopy AS7265x | Alamat I2C 0x49, catu 3,3 V |
| 3 | PIR HC-SR501 | Keluaran 3,3 V, catu 5 sampai 20 V |
| 4 | Modul relay 1 kanal (kumparan 5 V) | Mengendalikan lampu halogen |
| 5 | Lampu halogen 12 V | Sumber cahaya transmisi |
| 6 | LCD 16x2 dengan modul I2C (PCF8574) | Alamat 0x27 (sebagian modul 0x3F) |
| 7 | Buzzer aktif 3,3 sampai 5 V | Berbunyi bila diberi tegangan (bukan buzzer pasif) |
| 8 | Adaptor 12 V 3 A + soket DC | Hanya untuk lampu halogen |
| 9 | Adaptor USB 5 V minimal 2 A + kabel USB-C | Catu ESP32, PIR, relay, LCD |
| 10 | Kabel jumper, terminal sekrup, PCB/papan | Kabel lampu minimal 0,75 mm² |

Motor conveyor memakai catu dan saklar sendiri, terpisah dari rangkaian ini.

## 2. Skema blok

```
                        ┌───────────────────────────── ESP32 DevKit ─────────────────────────────┐
  Adaptor USB 5 V ──USB─┤ USB-C                                                                  │
                        │                                                                        │
                        │ 3V3 ───────────┬──────────────────────── VCC  AS7265x                  │
                        │ GPIO21 (SDA) ──┼──────────────────────── SDA  AS7265x                  │
                        │ GPIO22 (SCL) ──┼──────────────────────── SCL  AS7265x                  │
                        │                │                                                       │
                        │ VIN (5 V) ─────┼──┬──┬───────────────── VCC  PIR HC-SR501              │
                        │ GPIO27 ────────┼──┼──┼───────────────── OUT  PIR HC-SR501              │
                        │                │  │  │                                                 │
                        │                │  │  └───────────────── VCC  Relay                     │
                        │ GPIO4 ─────────┼──┼──────────────────── IN   Relay                     │
                        │                │  │                                                    │
                        │                │  └──────────────────── VCC  LCD I2C  (lihat 4.2)      │
                        │ GPIO13 (SDA) ──┼─────────────────────── SDA  LCD I2C                   │
                        │ GPIO14 (SCL) ──┼─────────────────────── SCL  LCD I2C                   │
                        │                │                                                       │
                        │ GPIO25 ────────┼─────────────────────── (+)  Buzzer aktif              │
                        │                │                                                       │
                        │ GND ───────────┴── GND semua modul: AS7265x, PIR, relay, LCD, buzzer (−)│
                        └────────────────────────────────────────────────────────────────────────┘

  Sirkuit lampu (terpisah dari catu ESP32, hanya lewat kontak relay):

     Adaptor 12 V (+) ──────── COM ┐
                                   │ kontak relay
                        Halogen ── NO ┘         NC: tidak dipakai
     Adaptor 12 V (−) ──────── Halogen (−)
```

Dua jalur I2C dipakai terpisah: sensor di GPIO 21/22 dan LCD di GPIO 13/14. Pemisahan ini disengaja, supaya gangguan pada LCD tidak membuat pembacaan sensor macet.

## 3. Tabel koneksi

| No | Komponen | Pin komponen | Sambung ke | Fungsi |
|---|---|---|---|---|
| 1 | AS7265x | SDA | GPIO 21 | Data I2C sensor |
| | | SCL | GPIO 22 | Clock I2C sensor |
| | | 3V3 / VCC | 3V3 ESP32 | Catu daya |
| | | GND | GND ESP32 | Ground |
| 2 | PIR HC-SR501 | OUT | GPIO 27 | Sinyal buah terdeteksi (HIGH) |
| | | VCC | VIN (5 V) | Catu daya |
| | | GND | GND ESP32 | Ground |
| 3 | Relay 1 kanal | IN | GPIO 4 | Kendali lampu (aktif LOW) |
| | | VCC | **VIN (5 V)** | Catu kumparan relay |
| | | GND | GND ESP32 | Ground |
| | | COM | Adaptor 12 V (+) | Sumber lampu |
| | | NO | Halogen (+) | Lampu menyala saat relay aktif |
| 4 | LCD 16x2 I2C | SDA | GPIO 13 | Data I2C LCD |
| | | SCL | GPIO 14 | Clock I2C LCD |
| | | VCC | **lihat 4.2** | Catu daya |
| | | GND | GND ESP32 | Ground |
| 5 | Buzzer aktif | (+) | GPIO 25 | Bunyi pola hasil |
| | | (−) | GND ESP32 | Ground |
| 6 | Halogen 12 V | (+) | NO relay | Beban relay |
| | | (−) | Adaptor 12 V (−) | Kembali ke adaptor |
| 7 | Tombol BOOT (di board) | GPIO 0 | bawaan board | Ditahan 3 detik saat menyala: lupakan WiFi |

## 4. Catatan penting (berbeda dengan draf laporan)

### 4.1 Relay memakai 5 V, bukan 3,3 V

Draf menulis VCC relay 3,3 V. Modul relay 1 kanal yang umum memakai kumparan 5 V (tertulis SRD-05VDC di relay), sehingga pada 3,3 V relay bisa tidak menarik atau berbunyi tetapi kontaknya tidak menutup. Firmware dataset (`buahsafe/buahsafe.ino`) sudah terbukti berjalan dengan relay VCC 5 V dan IN langsung dari GPIO. Pada susunan itu modul bersifat **aktif LOW**, dan firmware sudah menyesuaikan (`RELAY_ACTIVE_LOW 1`).

Bila lampu tetap menyala atau tidak padam sempurna saat alat diam:
1. Ubah `RELAY_ACTIVE_LOW` ke 0 di `config.h`, lalu flash ulang.
2. Bila tetap tidak padam, logika 3,3 V ESP32 tidak cukup untuk modul tersebut. Ganti dengan modul relay yang mendukung pemicu 3,3 V (bertuliskan "3.3V trigger" atau memiliki jumper JD-VCC).

### 4.2 Tegangan LCD

Draf menulis VCC LCD 3,3 V. Kebanyakan LCD 16x2 dengan modul PCF8574 dirancang untuk 5 V; pada 3,3 V tulisan bisa sangat pudar walau kontras sudah diputar maksimal.

- Bila LCD purwarupa sudah terbaca jelas pada 3,3 V, pertahankan.
- Bila pudar, pindahkan VCC LCD ke VIN (5 V). Modul I2C punya resistor pull-up ke VCC, sehingga SDA/SCL ikut bertegangan 5 V, padahal pin ESP32 bekerja pada 3,3 V. Pilihan yang aman: pasang *level shifter* I2C dua arah di antara LCD dan GPIO 13/14, atau lepas dua resistor pull-up di modul dan pasang 4,7 kΩ dari SDA dan SCL ke 3V3.

### 4.3 Daya lampu halogen

Periksa daya lampu yang dipakai: arus = daya ÷ 12 V. Lampu 20 W menarik sekitar 1,7 A (aman untuk adaptor 3 A), sedangkan lampu 35 W menarik sekitar 2,9 A dan arus awal filamen dingin bisa beberapa kali lipat, sehingga adaptor 3 A terlalu pas. Kontak relay umum tahan 10 A. Lampu 2 cm dari buah menghasilkan panas; bila memakai `LAMP_MODE 1` (lampu menyala terus), pantau suhu buah dan rangka.

### 4.4 Catu ESP32

ESP32 diberi daya lewat USB-C dari adaptor 5 V. Pin VIN lalu mengeluarkan sekitar 5 V untuk PIR, relay, dan LCD. Jangan menyambungkan adaptor 12 V ke VIN atau 3V3. Bila ingin memakai satu adaptor saja, pakai modul *step-down* (misalnya LM2596 atau MP1584) yang disetel ke 5,0 V dengan multimeter **sebelum** disambungkan ke VIN, dan satukan ground-nya.

### 4.5 Buzzer

Firmware menyalakan buzzer dengan memberi HIGH pada GPIO 25, sehingga yang cocok adalah **buzzer aktif**. Buzzer pasif hanya berbunyi "klik". Buzzer aktif kecil menarik sekitar 20 sampai 30 mA, masih aman untuk GPIO. Buzzer yang lebih keras perlu transistor NPN (misalnya 2N2222 dengan resistor basis 1 kΩ).

## 5. Urutan merakit dan menguji

Kerjakan bertahap dan uji tiap tahap sebelum menambah komponen berikutnya. Semua uji dilihat di Serial Monitor (115200 baud) dan LCD.

1. **ESP32 saja.** Colok USB, lalu flash firmware. Serial menampilkan `BOOT,BUAHSAFE_CONVEYOR,2.2.0-conveyor` dan baris `CFG,...` berisi setelan aktif.
2. **LCD.** Sambungkan LCD, lalu nyalakan ulang. LCD menampilkan `BuahSafe / Init AS7265x...`. Bila LCD menyala tetapi kosong, putar potensiometer kontras di belakang modul. Bila tetap kosong, coba `LCD_ADDRESS 0x3F` di `config.h`.
3. **AS7265x.** Sambungkan sensor, lalu nyalakan ulang. Bila LCD menampilkan `ERROR AS7265x / 0x49 tdk ada`, periksa SDA/SCL tertukar atau kabel longgar.
4. **WiFi.** Saat pertama kali, LCD menampilkan `Setup WiFi HP ke / BuahSafe-Setup`. Sambungkan HP ke hotspot itu dan pilih WiFi lokasi. Setelah tersambung, LCD menampilkan `BuahSafe siap / Jalankan belt` dan web menampilkan "Alat terhubung".
5. **Relay dan lampu (adaptor 12 V belum dicolok).** Lambaikan tangan di depan PIR: relay harus berbunyi klik sekali dan lampu indikator modul relay menyala sesaat. Ukur kontak COM-NO dengan multimeter mode tembus: tersambung hanya saat relay aktif.
6. **Lampu.** Colok adaptor 12 V, lalu picu PIR: lampu menyala sesaat dan padam kembali. Bila lampu malah menyala terus, lihat 4.1.
7. **PIR.** Tunggu 30 sampai 60 detik setelah alat menyala (PIR menstabilkan diri). Putar potensiometer **Tx** (waktu tahan) ke minimum dan **Sx** (jarak) sesuai lebar belt. Pasang jumper mode ke **H** (picu berulang) bila tersedia.
8. **Buzzer.** Setiap buah yang terbaca memberi 1 bip pendek (deteksi), lalu pola hasil: 1 bip normal, 3 bip panjang anomali, 2 bip berulang gagal dinilai.
9. **Uji satu buah.** Lewatkan satu jambu. Serial menampilkan baris `DATA,...`, `WAKTU,...`, dan `HASIL,200,<nomor>,<putusan>,<keyakinan>`, dan buah yang sama muncul di halaman Antrean web.

Setelah semua tahap lulus, lanjutkan ke kalibrasi jeda lampu dan PIR di [DEPLOY_SERVER_WIFI.md](DEPLOY_SERVER_WIFI.md) bagian "Kalibrasi di lokasi".

## 6. Gangguan yang sering terjadi

| Gejala | Kemungkinan penyebab | Tindakan |
|---|---|---|
| ESP32 menyala ulang saat lampu menyala | Tegangan turun atau lonjakan dari relay/lampu | Pisahkan catu lampu dari ESP32 (sudah dalam skema); pastikan adaptor USB minimal 2 A; jauhkan kabel lampu dari kabel I2C |
| `ERROR AS7265x` muncul sesekali | Kabel I2C terlalu panjang atau dekat kabel lampu/motor | Kabel I2C maksimal sekitar 30 cm, dipilin dengan GND |
| Satu buah terhitung dua kali | PIR memicu ulang | Putar Tx ke minimum, naikkan `TRIGGER_COOLDOWN_MS` |
| Buah tidak terdeteksi | PIR membaca panas tubuh, sedangkan jambu bersuhu ruang | Ganti dengan sensor halangan IR E18-D80NK (`TRIGGER_ACTIVE_LEVEL LOW`) |
| Banyak `GAGAL` beruntun | Buah terlalu rapat atau internet lambat | Beri jarak antarbuah sekitar 1 detik; periksa sinyal WiFi di Pengaturan > Perangkat |
