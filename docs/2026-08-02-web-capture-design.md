# BuahSafe Web Capture — Design

## Tujuan

Aplikasi lokal untuk memicu satu pengukuran AS7265x dari browser, menyimpan 18
kanal mentah terkalibrasi bersama ID jambu, menampilkan riwayat spektrum, mengisi label opsional,
dan mengekspor dataset ke CSV. Conveyor dan lampu halogen tetap dioperasikan di luar
ESP32 (atau via pin relay yang dikontrol oleh firmware).

## Arsitektur

- ESP32 menerima perintah `PING` dan `SCAN` melalui USB serial 115200 baud.
- LCD menggunakan bus I2C 0 pada SDA GPIO13 dan SCL GPIO14 (0x27).
- Sensor Triad AS7265x menggunakan bus I2C 1 pada SDA GPIO21 dan SCL GPIO22 (0x49).
- Flask menjadi satu-satunya pemilik port serial agar tidak terjadi konflik.
- Setiap `SCAN` berhasil ditulis ke SQLite sebelum dikirim ke antarmuka.
- Browser berkomunikasi dengan Flask melalui JSON API lokal.
- CSV dibuat dari isi SQLite saat pengguna menekan ekspor.

## Kanal Spektral AS7265x (18 Kanal)

1. AS72651: 410, 435, 460, 485, 510, 535 nm
2. AS72652: 560, 585, 610, 645, 680, 705 nm
3. AS72653: 730, 760, 810, 860, 900, 940 nm

## Data

Setiap pengukuran berisi timestamp laptop, ID jambu, nomor scan firmware,
18 nilai spektral (`nm410` s.d. `nm940`), dan label kosong/bagus/rusak.

## Keadaan gagal

Tombol scan nonaktif ketika ESP32 belum terhubung. Timeout, perangkat terlepas,
data serial salah, dan AS7265x tidak siap ditampilkan tanpa membuat baris database
palsu. Dashboard mendukung hapus baris (satu atau beberapa sekaligus lewat
seleksi) dengan dialog konfirmasi wajib; penghapusan bersifat permanen (tidak
ada undo/trash), jadi operator disarankan ekspor CSV secara berkala sebelum
membersihkan data uji coba.

## Pengoperasian

Pengguna memilih port COM, menghubungkan ESP32, memasukkan ID jambu, lalu menekan
tombol scan. Satu klik menghasilkan satu bunyi, satu pembacaan, dan satu record.
Dataset dapat diekspor kapan saja dan label dapat diubah langsung pada tabel.
