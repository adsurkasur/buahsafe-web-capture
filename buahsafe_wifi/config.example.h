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
