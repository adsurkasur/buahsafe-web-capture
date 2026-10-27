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
// BuahSafe - firmware conveyor (ESP32 di mitra, server terpisah)
//
// Board  : ESP32-WROOM-32 DevKit (USB-C, CP2102) -> "ESP32 Dev Module"
// Alat   : belt conveyor berjalan terus (motor bersaklar sendiri). Sensor
//          pemicu (PIR HC-SR501, GPIO 27) mendeteksi buah -> lampu halogen
//          (relay GPIO 4) menyala -> AS7265x mengukur saat buah lewat ->
//          hasil dikirim ke server -> LCD + buzzer memberi tahu operator di
//          ujung belt, sama dengan antrean di layar web.
//
// Protokol server:
//   GET  /api/device/poll?fw=..       detak tiap 10 dtk (204 = OK)
//   POST /api/device/auto-scan        {"line":"DATA,<n>,<18 nilai>","fw","trigger_ms","measure_ms",
//                                      "settle_ms","samples","lamp_mode"}
//                                     atau {"error":"...","fw"} bila buah gagal diukur
//                                     -> {"seq":57,"fruit_id":"CV-..","result":"NORMAL|ANOMALI|GAGAL"}
//
// Setiap buah yang memicu sensor SELALU dilaporkan (berhasil atau gagal) agar
// nomor urut di LCD/web sama dengan urutan buah di belt.
//
// Kalibrasi di lokasi (lihat docs/DEPLOY_SERVER_WIFI.md): SEMUA kenop ada di
// config.h (lihat config.example.h). Server mencatat trigger_ms, measure_ms, dan
// setelan yang dipakai tiap buah, jadi hasil antarsetelan bisa dibandingkan.
// Serial Monitor (115200) mencetak CFG saat boot dan baris DATA tiap buah.
//
// AS7265x mengirim 18 kanal (format sama dengan dataset); model di server hanya
// memakai 6 kanal NIR (610-860 nm). Gain dan integrasi bawaan SAMA dengan
// firmware akuisisi dataset (buahsafe/buahsafe.ino); jangan diubah tanpa
// mengambil ulang data latih.
//
// WiFi mitra diatur lewat hotspot "BuahSafe-Setup" (tanpa flashing ulang).
// Tahan tombol BOOT 3 detik saat dinyalakan untuk melupakan WiFi.
// ============================================================

#define FIRMWARE_VERSION "2.2.0-conveyor"

// ---- Kenop perangkat keras: nilai bawaan, bisa ditimpa di config.h ----
#ifndef TRIGGER_PIN
#define TRIGGER_PIN 27            // PIR HC-SR501 OUT (draf laporan, Tabel Koneksi)
#endif
#ifndef TRIGGER_ACTIVE_LEVEL
#define TRIGGER_ACTIVE_LEVEL HIGH // PIR: HIGH saat mendeteksi. Sensor halangan IR (E18-D80NK): LOW
#endif
#ifndef RELAY_PIN
#define RELAY_PIN 4               // relay lampu halogen
#endif
#ifndef RELAY_ACTIVE_LOW
#define RELAY_ACTIVE_LOW 1        // modul relay umum aktif-LOW; ubah ke 0 bila lampu justru menyala saat idle
#endif
#ifndef LAMP_SETTLE_MS
#define LAMP_SETTLE_MS 300        // jeda lampu menyala -> mulai ukur. KENOP UTAMA kalibrasi belt
#endif
#ifndef TRIGGER_COOLDOWN_MS
#define TRIGGER_COOLDOWN_MS 1500  // abaikan picu ulang dari buah yang sama
#endif
#ifndef MAX_TRIGGER_AGE_MS
#define MAX_TRIGGER_AGE_MS 700    // picu lebih tua dari ini saat siap ukur = buah sudah lewat -> GAGAL
#endif

#ifndef LAMP_MODE
#define LAMP_MODE 0               // 0 = lampu menyala hanya saat buah terpicu; 1 = menyala terus selama alat siap
#endif
#ifndef MEASURE_SAMPLES
#define MEASURE_SAMPLES 1         // jumlah pengukuran yang dirata-ratakan per buah (dataset: 1)
#endif
#ifndef DETECT_BEEP
#define DETECT_BEEP 1             // 1 = bip pendek saat buah terdeteksi
#endif
#ifndef BUZZER_PIN
#define BUZZER_PIN 25
#endif
#ifndef LCD_SDA_PIN
#define LCD_SDA_PIN 13
#endif
#ifndef LCD_SCL_PIN
#define LCD_SCL_PIN 14
#endif
#ifndef LCD_ADDRESS
#define LCD_ADDRESS 0x27          // sebagian modul LCD I2C memakai 0x3F
#endif
#ifndef SENSOR_SDA_PIN
#define SENSOR_SDA_PIN 21
#endif
#ifndef SENSOR_SCL_PIN
#define SENSOR_SCL_PIN 22
#endif
#ifndef SENSOR_GAIN
#define SENSOR_GAIN AS7265X_GAIN_64X  // sama dengan dataset
#endif
#ifndef SENSOR_INTEGRATION_CYCLES
#define SENSOR_INTEGRATION_CYCLES 50  // sama dengan dataset (x 2,8 ms)
#endif
#ifndef HEARTBEAT_MS
#define HEARTBEAT_MS 10000        // server menganggap alat putus bila >25 dtk tanpa detak
#endif

constexpr uint8_t BOOT_BUTTON_PIN = 0;
constexpr uint32_t HTTP_TIMEOUT_MS = 8000;
constexpr uint32_t HTTP_CONNECT_TIMEOUT_MS = 6000;
constexpr uint16_t SETUP_PORTAL_TIMEOUT_S = 300;
constexpr uint32_t WDT_TIMEOUT_S = 45;

// Pola buzzer: pasangan {nyala ms, diam ms}, diakhiri {0,0}
struct Tone { uint16_t on, off; };
const Tone BEEP_DETECT[] = {{60, 0}, {0, 0}};
const Tone BEEP_NORMAL[] = {{120, 0}, {0, 0}};
const Tone BEEP_ANOMALI[] = {{500, 200}, {500, 200}, {500, 0}, {0, 0}};
const Tone BEEP_FAILED[] = {{100, 100}, {100, 400}, {100, 100}, {100, 0}, {0, 0}};

LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);
AS7265X spectralSensor;
TwoWire sensorWire = TwoWire(1);
WiFiClientSecure tls;
HTTPClient http;

bool sensorReady = false;
uint32_t scanNumber = 0;
uint32_t lastHeartbeat = 0;
uint32_t lastTriggerStart = 0;

// Diisi interrupt: picu tidak hilang walau ESP32 sedang mengirim HTTP
volatile bool triggerPending = false;
volatile uint32_t triggerAt = 0;
volatile uint32_t triggerActiveMs = 0;

// Buzzer non-blocking: pola ANOMALI (~2 dtk) tidak boleh membuat buah berikutnya terlewat
const Tone *tonePattern = nullptr;
uint8_t toneStep = 0;
bool toneOn = false;
uint32_t toneNextAt = 0;

// ============================================================
// Perangkat keras
// ============================================================

void setRelay(bool on) {
  digitalWrite(RELAY_PIN, (on != (RELAY_ACTIVE_LOW == 1)) ? HIGH : LOW);
}

// LAMP_MODE 1: lampu tetap menyala sehingga tidak perlu menunggu filamen memanas tiap buah
void lampIdle() {
  setRelay(LAMP_MODE == 1 && sensorReady);
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

void playTone(const Tone *pattern) {
  tonePattern = pattern;
  toneStep = 0;
  toneOn = true;
  digitalWrite(BUZZER_PIN, HIGH);
  toneNextAt = millis() + pattern[0].on;
}

void updateTone() {
  if (!tonePattern || millis() < toneNextAt) return;
  const Tone &t = tonePattern[toneStep];
  if (toneOn) {
    digitalWrite(BUZZER_PIN, LOW);
    toneOn = false;
    toneNextAt = millis() + t.off;
    return;
  }
  toneStep++;
  if (tonePattern[toneStep].on == 0) {
    tonePattern = nullptr;
    return;
  }
  digitalWrite(BUZZER_PIN, HIGH);
  toneOn = true;
  toneNextAt = millis() + tonePattern[toneStep].on;
}

void IRAM_ATTR onTriggerChange() {
  const uint32_t now = millis();
  if (digitalRead(TRIGGER_PIN) == TRIGGER_ACTIVE_LEVEL) {
    if (!triggerPending && now - lastTriggerStart >= TRIGGER_COOLDOWN_MS) {
      triggerPending = true;
      triggerAt = now;
      triggerActiveMs = 0;
      lastTriggerStart = now;
    }
  } else if (now >= triggerAt) {
    triggerActiveMs = now - triggerAt;
  }
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

// Lampu menyala, tunggu stabil, ukur saat buah lewat. Isi `line` dengan baris DATA.
void measure(char *line, size_t size) {
  setRelay(true);
  const uint32_t lampOnAt = millis();
  if (DETECT_BEEP) {
    digitalWrite(BUZZER_PIN, HIGH);  // bip deteksi berbarengan dengan jeda lampu
    delay(BEEP_DETECT[0].on);
    digitalWrite(BUZZER_PIN, LOW);
  }
  // Mode nyala terus: lampu sudah stabil, jeda hanya untuk mode nyala-saat-picu
  const uint32_t settle = LAMP_MODE == 1 ? 0 : LAMP_SETTLE_MS;
  while (millis() - lampOnAt < settle) delay(1);

  // Urutan sama dengan dataset: 410,435,460,485,510,535,560,585,610,645,680,705,730,760,810,860,900,940 nm
  float sum[18] = {0};
  for (uint8_t n = 0; n < MEASURE_SAMPLES; n++) {
    // Satu takeMeasurements() per sampel: memicu ketiga device terpisah terbukti
    // membuat board hang (lihat catatan panjang di ../buahsafe.ino)
    spectralSensor.takeMeasurements();
    const float v[18] = {
      spectralSensor.getCalibratedA(), spectralSensor.getCalibratedB(),
      spectralSensor.getCalibratedC(), spectralSensor.getCalibratedD(),
      spectralSensor.getCalibratedE(), spectralSensor.getCalibratedF(),
      spectralSensor.getCalibratedG(), spectralSensor.getCalibratedH(),
      spectralSensor.getCalibratedR(), spectralSensor.getCalibratedI(),
      spectralSensor.getCalibratedS(), spectralSensor.getCalibratedJ(),
      spectralSensor.getCalibratedT(), spectralSensor.getCalibratedU(),
      spectralSensor.getCalibratedV(), spectralSensor.getCalibratedW(),
      spectralSensor.getCalibratedK(), spectralSensor.getCalibratedL(),
    };
    for (uint8_t i = 0; i < 18; i++) sum[i] += v[i];
  }
  lampIdle();
  scanNumber++;

  // Stack buffer tanpa String: hindari fragmentasi heap
  int at = snprintf(line, size, "DATA,%lu", static_cast<unsigned long>(scanNumber));
  for (uint8_t i = 0; i < 18 && at > 0 && static_cast<size_t>(at) < size; i++) {
    at += snprintf(line + at, size - at, ",%.6f", sum[i] / MEASURE_SAMPLES);
  }
}

void printConfig() {
  Serial.printf("CFG,fw=%s,trigger_pin=%d,trigger_level=%d,relay_pin=%d,relay_active_low=%d,"
                "lamp_mode=%d,lamp_settle_ms=%d,samples=%d,gain=%d,integration=%d,"
                "cooldown_ms=%d,max_trigger_age_ms=%d,heartbeat_ms=%d\n",
                FIRMWARE_VERSION, TRIGGER_PIN, TRIGGER_ACTIVE_LEVEL, RELAY_PIN, RELAY_ACTIVE_LOW,
                LAMP_MODE, LAMP_SETTLE_MS, MEASURE_SAMPLES, SENSOR_GAIN, SENSOR_INTEGRATION_CYCLES,
                TRIGGER_COOLDOWN_MS, MAX_TRIGGER_AGE_MS, HEARTBEAT_MS);
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
    }
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  wm.setConfigPortalTimeout(SETUP_PORTAL_TIMEOUT_S);
  wm.setAPCallback([](WiFiManager *) {
    setLcdLines("Setup WiFi HP ke", "BuahSafe-Setup");
  });

  setLcdLines("Menyambung WiFi", "...");
  esp_task_wdt_delete(NULL);  // portal setup bisa menunggu mitra sampai 5 menit
  const bool ok = wm.autoConnect("BuahSafe-Setup", BUAHSAFE_SETUP_AP_PASSWORD);
  esp_task_wdt_add(NULL);

  if (!ok) {
    setLcdLines("WiFi gagal", "Mulai ulang...");
    delay(2000);
    ESP.restart();
  }
}

// Ambil nilai "key":"value" atau "key":angka dari JSON datar balasan server
String jsonField(const String &body, const char *key) {
  const String needle = String("\"") + key + "\":";
  int at = body.indexOf(needle);
  if (at < 0) return String();
  at += needle.length();
  while (at < (int)body.length() && body[at] == ' ') at++;
  if (at < (int)body.length() && body[at] == '"') {
    const int end = body.indexOf('"', at + 1);
    return end < 0 ? String() : body.substring(at + 1, end);
  }
  int end = at;
  while (end < (int)body.length() && body[end] != ',' && body[end] != '}') end++;
  return body.substring(at, end);
}

// Laporkan satu buah ke server lalu tampilkan hasilnya di LCD + buzzer.
void reportFruit(const char *line, const char *error, uint32_t triggerMs, uint32_t measureMs) {
  static char body[600];
  if (error) {
    snprintf(body, sizeof(body), "{\"error\":\"%s\",\"fw\":\"%s\"}", error, FIRMWARE_VERSION);
  } else {
    snprintf(body, sizeof(body),
             "{\"line\":\"%s\",\"fw\":\"%s\",\"trigger_ms\":%lu,\"measure_ms\":%lu,"
             "\"settle_ms\":%d,\"samples\":%d,\"lamp_mode\":%d}",
             line, FIRMWARE_VERSION, static_cast<unsigned long>(triggerMs), static_cast<unsigned long>(measureMs),
             LAMP_MODE == 1 ? 0 : LAMP_SETTLE_MS, MEASURE_SAMPLES, LAMP_MODE);
  }

  esp_task_wdt_reset();
  http.begin(tls, BUAHSAFE_SERVER_URL "/api/device/auto-scan");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", BUAHSAFE_DEVICE_KEY);
  const int code = http.POST(reinterpret_cast<uint8_t *>(body), strlen(body));
  const String response = code > 0 ? http.getString() : String();
  http.end();

  const String seq = jsonField(response, "seq");
  const String result = jsonField(response, "result");
  Serial.printf("HASIL,%d,%s,%s,%s\n", code, seq.c_str(), result.c_str(), jsonField(response, "confidence").c_str());
  char line1[17], line2[17];
  snprintf(line2, sizeof(line2), "Yakin %s%%", jsonField(response, "confidence").c_str());
  if (code == 200 && result == "NORMAL") {
    snprintf(line1, sizeof(line1), "#%s NORMAL", seq.c_str());
    setLcdLines(line1, line2);
    playTone(BEEP_NORMAL);
  } else if (code == 200 && result == "ANOMALI") {
    snprintf(line1, sizeof(line1), "#%s ANOMALI", seq.c_str());
    setLcdLines(line1, line2);
    playTone(BEEP_ANOMALI);
  } else {
    // Gagal ukur, model gagal, atau server tak terjangkau: buah disisihkan, tidak ditebak
    if (seq.length()) snprintf(line1, sizeof(line1), "#%s GAGAL", seq.c_str());
    else snprintf(line1, sizeof(line1), "GAGAL KIRIM %d", code);
    setLcdLines(line1, "Sisihkan buah");
    playTone(BEEP_FAILED);
  }
}

void heartbeat() {
  char url[200];
  snprintf(url, sizeof(url), "%s/api/device/poll?fw=%s&rssi=%d&ip=%s",
           BUAHSAFE_SERVER_URL, FIRMWARE_VERSION, WiFi.RSSI(), WiFi.localIP().toString().c_str());
  http.begin(tls, url);
  http.addHeader("X-Device-Key", BUAHSAFE_DEVICE_KEY);
  const int code = http.GET();
  http.end();
  if (code == 401) setLcdLines("Kunci alat salah", "Hubungi admin");
  else if (code == 423) setLcdLines("Alat diputus", "oleh pemilik");  // Pengaturan > Perangkat di web
  else if (code != 204 && code != 200) {
    char line2[17];
    snprintf(line2, sizeof(line2), "Server: %d", code);  // negatif = galat koneksi/TLS
    setLcdLines("Server tdk jawab", line2);
  }
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
  Serial.println("BOOT,BUAHSAFE_CONVEYOR," FIRMWARE_VERSION);
  printConfig();

  Wire.begin(LCD_SDA_PIN, LCD_SCL_PIN);
  Wire.setClock(100000);
  Wire.setTimeOut(1000);
  lcd.init();
  lcd.backlight();
  setLcdLines("BuahSafe", "Init AS7265x...");
  sensorReady = initSensor();
  lampIdle();

  startWifi();
  tls.setCACert(ROOT_CA_BUNDLE);
  tls.setHandshakeTimeout(HTTP_CONNECT_TIMEOUT_MS / 1000);
  http.setReuse(true);  // sesi TLS dipakai ulang: tanpa handshake 1-2 dtk per buah
  http.setConnectTimeout(HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  heartbeat();
  lastHeartbeat = millis();
  // PIR HC-SR501 butuh ~30-60 dtk menstabilkan diri setelah dinyalakan
  pinMode(TRIGGER_PIN, TRIGGER_ACTIVE_LEVEL == HIGH ? INPUT_PULLDOWN : INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(TRIGGER_PIN), onTriggerChange, CHANGE);
  setLcdLines(sensorReady ? "BuahSafe siap" : "ERROR AS7265x", sensorReady ? "Jalankan belt" : "Hubungi teknisi");
}

void loop() {
  esp_task_wdt_reset();
  updateTone();

  if (triggerPending) {
    const uint32_t age = millis() - triggerAt;
    if (WiFi.status() != WL_CONNECTED) {
      triggerPending = false;
      setLcdLines("WiFi terputus", "Sisihkan buah");
      playTone(BEEP_FAILED);
    } else if (!sensorReady) {
      triggerPending = false;
      reportFruit(nullptr, "AS7265X_NOT_READY", 0, 0);
    } else if (age > MAX_TRIGGER_AGE_MS) {
      // ESP32 masih sibuk mengirim buah sebelumnya saat buah ini lewat: jangan ukur terlambat
      triggerPending = false;
      reportFruit(nullptr, "TERLAMBAT_UKUR", 0, 0);
    } else {
      static char line[420];
      measure(line, sizeof(line));
      const uint32_t measureMs = millis() - triggerAt;
      const uint32_t activeMs = triggerActiveMs ? triggerActiveMs : measureMs;  // sinyal masih aktif
      triggerPending = false;
      Serial.printf("%s\nWAKTU,trigger_ms=%lu,measure_ms=%lu\n", line,
                    static_cast<unsigned long>(activeMs), static_cast<unsigned long>(measureMs));
      reportFruit(line, nullptr, activeMs, measureMs);
    }
    lastHeartbeat = millis();
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    setLcdLines("WiFi terputus", "Menyambung ulang");
    delay(200);
    return;
  }
  if (millis() - lastHeartbeat >= HEARTBEAT_MS && !tonePattern) {
    heartbeat();
    lastHeartbeat = millis();
  }
}
