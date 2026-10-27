// Salin berkas ini menjadi config.h (config.h TIDAK masuk Git), lalu isi nilainya.
#pragma once

// URL server BuahSafe (HTTPS lewat Cloudflare Tunnel), tanpa garis miring di akhir
#define BUAHSAFE_SERVER_URL "https://buahsafe-api.adsurkasur.my.id"

// Harus sama persis dengan BUAHSAFE_DEVICE_KEY di server (/etc/buahsafe/buahsafe.env)
#define BUAHSAFE_DEVICE_KEY "ganti-dengan-kunci-acak-panjang"

// Kode perangkat, sama dengan BUAHSAFE_DEVICE_ID di server
#define BUAHSAFE_DEVICE_ID "BSF-001"

// Sandi hotspot setup "BuahSafe-Setup" (minimal 8 karakter) yang muncul saat alat
// belum kenal WiFi mitra. Berikan ke mitra bersama panduan pemasangan.
#define BUAHSAFE_SETUP_AP_PASSWORD "ganti-sandi-setup"

// ============================================================
// KENOP KALIBRASI (opsional). Hapus "//" di depan baris untuk menimpa nilai bawaan,
// lalu flash ulang. Nilai yang dipakai tercetak di Serial Monitor (baris CFG) dan
// ikut terkirim ke server tiap buah. Panduan: docs/DEPLOY_SERVER_WIFI.md "Kalibrasi".
// ============================================================

// ---- Pemicu (PIR HC-SR501 atau sensor halangan IR) ----
// #define TRIGGER_PIN 27            // pin OUT sensor pemicu
// #define TRIGGER_ACTIVE_LEVEL HIGH // PIR: HIGH. Sensor halangan IR E18-D80NK: LOW
// #define TRIGGER_COOLDOWN_MS 1500  // abaikan picu ulang dari buah yang sama (ms)
// #define MAX_TRIGGER_AGE_MS 700    // alat sibuk lebih lama dari ini -> buah dilaporkan GAGAL, bukan diukur terlambat

// ---- Lampu halogen (relay) ----
// #define RELAY_PIN 4               // pin IN relay
// #define RELAY_ACTIVE_LOW 1        // 0 bila lampu malah menyala saat alat diam
// #define LAMP_MODE 0               // 0 = nyala hanya saat buah terpicu; 1 = nyala terus selama alat siap
// #define LAMP_SETTLE_MS 300        // jeda lampu menyala -> ukur (hanya LAMP_MODE 0). KENOP UTAMA.
//                                   // Dataset diambil dengan jeda 3000 ms (lampu sudah terang penuh).
//                                   // Jeda yang terlalu pendek -> intensitas lebih rendah dari data latih.

// ---- Sensor AS7265x ----
// #define MEASURE_SAMPLES 1         // pengukuran dirata-ratakan per buah (dataset: 1). Tiap sampel ~0,4 dtk
// #define SENSOR_GAIN AS7265X_GAIN_64X       // JANGAN diubah tanpa mengambil ulang data latih
// #define SENSOR_INTEGRATION_CYCLES 50       // JANGAN diubah tanpa mengambil ulang data latih
// #define SENSOR_SDA_PIN 21
// #define SENSOR_SCL_PIN 22

// ---- LCD, buzzer, jaringan ----
// #define LCD_ADDRESS 0x27          // sebagian modul memakai 0x3F
// #define LCD_SDA_PIN 13
// #define LCD_SCL_PIN 14
// #define BUZZER_PIN 25
// #define DETECT_BEEP 1             // 0 = tanpa bip saat buah terdeteksi
// #define HEARTBEAT_MS 10000        // detak ke server (server menganggap putus bila >25 dtk)
