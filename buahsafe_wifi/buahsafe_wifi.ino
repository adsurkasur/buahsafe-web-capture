#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <WiFiManager.h>
#include <LiquidCrystal_I2C.h>
#include <SparkFun_AS7265X.h>
#include <esp_task_wdt.h>

#include "config.h"   // salin dari config.example.h
#include "root_ca.h"

// ============================================================
// BuahSafe - firmware WiFi (ESP32 di lokasi mitra, server terpisah)
//
// Board  : ESP32-WROOM-32 DevKit (USB-C, CP2102) -> pilih "ESP32 Dev Module"
// Wiring : sama dengan firmware USB (../buahsafe.ino), tidak ada perubahan.
//
// Alur (ESP32 di balik NAT mitra tidak bisa dihubungi server, jadi ESP32
// yang bertanya):
//   GET  /api/device/poll    long-poll <=10 s; 204 = tidak ada perintah,
//                            200 {"command":"SCAN","job":"..."} = pindai
//   POST /api/device/result  {"job":"...","line":"DATA,<n>,<18 nilai>"}
//                            atau {"job":"...","error":"..."}
//                            -> {"ok":true,"scan_no":<n|null>}
// Baris DATA identik dengan protokol serial sehingga validasi server sama.
//
// WiFi mitra diatur tanpa flashing ulang: saat belum kenal WiFi, alat
// membuka hotspot "BuahSafe-Setup"; sambungkan HP, pilih WiFi mitra.
// Tahan tombol BOOT saat alat dinyalakan (3 detik) untuk melupakan WiFi.
// ============================================================

#define FIRMWARE_VERSION "2.0.0-wifi"

constexpr uint8_t BUZZER_PIN = 25;
constexpr uint8_t RELAY_PIN = 26;
constexpr uint8_t BOOT_BUTTON_PIN = 0;

constexpr uint8_t LCD_SDA_PIN = 13;
constexpr uint8_t LCD_SCL_PIN = 14;
constexpr uint8_t SENSOR_SDA_PIN = 21;
constexpr uint8_t SENSOR_SCL_PIN = 22;

// Modul relay terbukti ACTIVE-LOW (lihat ../buahsafe.ino)
constexpr uint8_t RELAY_ON_LEVEL = LOW;
constexpr uint8_t RELAY_OFF_LEVEL = HIGH;

constexpr uint8_t LCD_ADDRESS = 0x27;
constexpr uint8_t SENSOR_GAIN = AS7265X_GAIN_64X;
constexpr uint8_t SENSOR_INTEGRATION_CYCLES = 50;
constexpr uint16_t SCAN_BEEP_MS = 180;
constexpr uint16_t SCAN_WARMUP_MS = 3000;

// Server menahan poll maksimal 10 s; beri ruang handshake TLS + latensi seluler
constexpr uint32_t HTTP_TIMEOUT_MS = 15000;
constexpr uint32_t HTTP_CONNECT_TIMEOUT_MS = 8000;
constexpr uint32_t BACKOFF_MAX_MS = 30000;
constexpr uint16_t SETUP_PORTAL_TIMEOUT_S = 300;
// Lebih panjang dari skenario terlama: poll 15 s, atau scan ~5 s + POST 15 s
constexpr uint32_t WDT_TIMEOUT_S = 45;

LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);
AS7265X spectralSensor;
TwoWire sensorWire = TwoWire(1);
WiFiClientSecure tls;
HTTPClient http;

bool sensorReady = false;
uint32_t scanNumber = 0;
uint32_t backoffMs = 1000;
bool lastPollOk = false;

// ============================================================
// Perangkat keras
// ============================================================

void setRelay(bool enabled) {
  digitalWrite(RELAY_PIN, enabled ? RELAY_ON_LEVEL : RELAY_OFF_LEVEL);
}

void setLcdLines(const char *line1, const char *line2) {
  lcd.setCursor(0, 0);
  lcd.print("                ");
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print("                ");
  lcd.setCursor(0, 1);
  lcd.print(line2);
}

void beep(uint16_t ms) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(ms);
  digitalWrite(BUZZER_PIN, LOW);
}

bool initSensor() {
  if (!sensorWire.begin(SENSOR_SDA_PIN, SENSOR_SCL_PIN)) {
    setLcdLines("ERROR AS7265x", "I2C bus gagal");
    return false;
  }
  sensorWire.setClock(100000);
  sensorWire.setTimeOut(1000);

  sensorWire.beginTransmission(0x49);
  if (sensorWire.endTransmission() != 0) {
    setLcdLines("ERROR AS7265x", "0x49 tdk ada");
    return false;
  }
  if (!spectralSensor.begin(sensorWire)) {
    setLcdLines("ERROR AS7265x", "Init gagal");
    return false;
  }
  spectralSensor.setGain(SENSOR_GAIN);
  spectralSensor.setIntegrationCycles(SENSOR_INTEGRATION_CYCLES);
  spectralSensor.disableBulb(AS7265x_LED_WHITE);
  spectralSensor.disableBulb(AS7265x_LED_IR);
  spectralSensor.disableBulb(AS7265x_LED_UV);
  return true;
}

// Pindai satu buah; isi `line` dengan baris DATA (format sama dengan firmware USB).
void measure(char *line, size_t size) {
  setRelay(true);
  beep(SCAN_BEEP_MS);
  setLcdLines("Memindai...", "Jangan bergerak");

  // Tunggu lampu stabil; reset watchdog selama menunggu
  for (uint16_t waited = 0; waited < SCAN_WARMUP_MS; waited += 100) {
    esp_task_wdt_reset();
    delay(100);
  }

  // Satu takeMeasurements() saja: memicu ketiga device sekaligus terbukti
  // membuat board hang (lihat catatan panjang di ../buahsafe.ino)
  spectralSensor.takeMeasurements();
  setRelay(false);
  scanNumber++;

  // Stack buffer + satu snprintf: hindari realokasi heap String (penyebab korupsi
  // byte di field 460 nm pada versi lama)
  snprintf(
    line, size,
    "DATA,%lu,"
    "%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,"
    "%.6f,%.6f,%.6f,%.6f,%.6f,%.6f,"
    "%.6f,%.6f,%.6f,%.6f,%.6f,%.6f",
    static_cast<unsigned long>(scanNumber),
    spectralSensor.getCalibratedA(), spectralSensor.getCalibratedB(),
    spectralSensor.getCalibratedC(), spectralSensor.getCalibratedD(),
    spectralSensor.getCalibratedE(), spectralSensor.getCalibratedF(),
    spectralSensor.getCalibratedG(), spectralSensor.getCalibratedH(),
    spectralSensor.getCalibratedR(), spectralSensor.getCalibratedI(),
    spectralSensor.getCalibratedS(), spectralSensor.getCalibratedJ(),
    spectralSensor.getCalibratedT(), spectralSensor.getCalibratedU(),
    spectralSensor.getCalibratedV(), spectralSensor.getCalibratedW(),
    spectralSensor.getCalibratedK(), spectralSensor.getCalibratedL()
  );
}

// ============================================================
// Jaringan
// ============================================================

void startWifi() {
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  WiFiManager wm;

  if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
    setLcdLines("Tahan BOOT 3 dtk", "utk lupakan WiFi");
    delay(3000);
    if (digitalRead(BOOT_BUTTON_PIN) == LOW) {
      wm.resetSettings();
      setLcdLines("WiFi dilupakan", "Mulai ulang...");
      beep(400);
    }
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  wm.setConfigPortalTimeout(SETUP_PORTAL_TIMEOUT_S);
  wm.setAPCallback([](WiFiManager *) {
    setLcdLines("Setup WiFi HP ke", "BuahSafe-Setup");
  });

  setLcdLines("Menyambung WiFi", "...");
  // Watchdog dilepas selama portal setup (bisa sampai 5 menit menunggu mitra)
  esp_task_wdt_delete(NULL);
  const bool ok = wm.autoConnect("BuahSafe-Setup", BUAHSAFE_SETUP_AP_PASSWORD);
  esp_task_wdt_add(NULL);

  if (!ok) {
    setLcdLines("WiFi gagal", "Mulai ulang...");
    delay(2000);
    ESP.restart();
  }
}

// Ambil nilai string "key":"value" dari JSON datar balasan server (tanpa library JSON)
bool jsonString(const String &body, const char *key, char *out, size_t size) {
  String needle = String("\"") + key + "\":\"";
  int start = body.indexOf(needle);
  if (start < 0) return false;
  start += needle.length();
  int end = body.indexOf('"', start);
  if (end < 0 || static_cast<size_t>(end - start) >= size) return false;
  body.substring(start, end).toCharArray(out, size);
  return true;
}

// Kirim hasil; kembalikan scan_no sah dari database, 0 bila belum terkonfirmasi.
uint32_t postResult(const char *job, const char *line, const char *error) {
  static char body[512];
  if (error) {
    snprintf(body, sizeof(body), "{\"job\":\"%s\",\"error\":\"%s\"}", job, error);
  } else {
    snprintf(body, sizeof(body), "{\"job\":\"%s\",\"line\":\"%s\"}", job, line);
  }

  for (uint8_t attempt = 1; attempt <= 2; attempt++) {
    esp_task_wdt_reset();
    http.begin(tls, BUAHSAFE_SERVER_URL "/api/device/result");
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Key", BUAHSAFE_DEVICE_KEY);
    const int code = http.POST(reinterpret_cast<uint8_t *>(body), strlen(body));
    const String response = code > 0 ? http.getString() : String();
    http.end();

    if (code == 200) {
      const int at = response.indexOf("\"scan_no\":");
      return at < 0 ? 0 : static_cast<uint32_t>(strtoul(response.c_str() + at + 10, nullptr, 10));
    }
    if (code == 409) return 0;  // server sudah menyerah menunggu (timeout di sisi operator)
  }
  return 0;
}

void handleScan(const char *job) {
  if (!sensorReady) {
    postResult(job, nullptr, "AS7265X_NOT_READY");
    setLcdLines("ERROR AS7265x", "Hubungi teknisi");
    return;
  }

  static char line[420];
  measure(line, sizeof(line));
  setLcdLines("Mengirim data...", "");

  const uint32_t scanNo = postResult(job, line, nullptr);
  if (scanNo > 0) {
    char line2[17];
    snprintf(line2, sizeof(line2), "Scan #%lu OK", static_cast<unsigned long>(scanNo));
    setLcdLines("Data tersimpan", line2);
  } else {
    // Jujur: jangan tampilkan nomor yang belum terkonfirmasi database
    setLcdLines("Belum terkonfirm", "Cek layar web");
  }
}

void pollOnce() {
  char url[256];
  snprintf(url, sizeof(url), "%s/api/device/poll?fw=%s&rssi=%d&ip=%s",
           BUAHSAFE_SERVER_URL, FIRMWARE_VERSION, WiFi.RSSI(), WiFi.localIP().toString().c_str());

  http.begin(tls, url);
  http.addHeader("X-Device-Key", BUAHSAFE_DEVICE_KEY);
  const int code = http.GET();
  const String body = code == 200 ? http.getString() : String();
  http.end();

  if (code == 204 || code == 200) {
    if (!lastPollOk) setLcdLines("BuahSafe siap", "Menunggu scan");
    lastPollOk = true;
    backoffMs = 1000;
    char job[32];
    if (code == 200 && jsonString(body, "job", job, sizeof(job))) {
      handleScan(job);
    }
    return;
  }

  lastPollOk = false;
  if (code == 401) {
    setLcdLines("Kunci alat salah", "Hubungi admin");
    backoffMs = BACKOFF_MAX_MS;
  } else {
    char line2[17];
    snprintf(line2, sizeof(line2), "Server: %d", code);  // negatif = galat koneksi/TLS
    setLcdLines("Server tdk jawab", line2);
  }

  for (uint32_t waited = 0; waited < backoffMs; waited += 500) {
    esp_task_wdt_reset();
    delay(500);
  }
  backoffMs = min(backoffMs * 2, BACKOFF_MAX_MS);
}

// ============================================================
// Setup & loop
// ============================================================

void setupWatchdog() {
  esp_task_wdt_config_t wdtConfig = {
    .timeout_ms = WDT_TIMEOUT_S * 1000,
    .idle_core_mask = 0,
    .trigger_panic = true,
  };
  if (esp_task_wdt_reconfigure(&wdtConfig) != ESP_OK) {
    esp_task_wdt_init(&wdtConfig);
  }
  esp_task_wdt_add(NULL);
}

void setup() {
  setupWatchdog();
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  setRelay(false);

  Serial.begin(115200);
  Serial.println("BOOT,BUAHSAFE_WIFI," FIRMWARE_VERSION);

  Wire.begin(LCD_SDA_PIN, LCD_SCL_PIN);
  Wire.setClock(100000);
  Wire.setTimeOut(1000);
  lcd.init();
  lcd.backlight();
  setLcdLines("BuahSafe", "Init AS7265x...");

  sensorReady = initSensor();
  if (sensorReady) setLcdLines("BuahSafe", "Sensor siap");

  startWifi();

  tls.setCACert(ROOT_CA_BUNDLE);
  tls.setHandshakeTimeout(HTTP_CONNECT_TIMEOUT_MS / 1000);
  http.setReuse(true);  // pakai ulang sesi TLS: handshake ~1-2 s tidak diulang tiap poll
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
}

void loop() {
  esp_task_wdt_reset();

  if (WiFi.status() != WL_CONNECTED) {
    lastPollOk = false;
    setLcdLines("WiFi terputus", "Menyambung ulang");
    delay(1000);  // setAutoReconnect menangani sambung ulang
    return;
  }

  pollOnce();
}
