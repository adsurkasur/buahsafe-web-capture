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

// ---- Perangkat keras conveyor (opsional; hapus komentar untuk menimpa nilai bawaan) ----
// #define TRIGGER_PIN 27            // pin sensor pemicu (PIR HC-SR501 OUT)
// #define TRIGGER_ACTIVE_LEVEL HIGH // PIR: HIGH. Sensor halangan IR E18-D80NK: LOW
// #define RELAY_PIN 4               // relay lampu halogen
// #define RELAY_ACTIVE_LOW 1        // 0 bila lampu malah menyala saat alat diam
// #define LAMP_SETTLE_MS 300        // jeda lampu -> ukur; kalibrasi dengan trigger_ms di log server
// #define TRIGGER_COOLDOWN_MS 1500  // abaikan picu ulang dari buah yang sama
// #define MAX_TRIGGER_AGE_MS 700    // lewat batas ini buah dianggap sudah lewat -> GAGAL
