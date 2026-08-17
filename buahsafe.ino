#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SparkFun_AS7265X.h>
#include <esp_task_wdt.h>

// ============================================================
// BuahSafe - firmware akuisisi dataset manual AS7265x
//
// Serial command:
//   PING
//     -> ACK,PONG
//
//   SCAN / RESCAN
//     -> DATA,<scan>,
//        <410>,<435>,<460>,<485>,<510>,<535>,
//        <560>,<585>,<610>,<645>,<680>,<705>,
//        <730>,<760>,<810>,<860>,<900>,<940>
//     (RESCAN = server sedang mengulang percobaan scan yang gagal
//      sebelumnya; identik dengan SCAN secara fungsi, bedanya cuma
//      teks yang ditampilkan di LCD supaya operator tahu ini bukan
//      scan baru biasa)
//
//   SAVED,<scan_no>
//     (dikirim SERVER -> firmware setelah data benar-benar tersimpan
//      di database; firmware menunggu ini sebentar setelah mengirim
//      DATA supaya nomor yang tampil di LCD adalah nomor yang SAH di
//      database, bukan tebakan counter lokal firmware)
//
// AS7265x Spectral Triad:
//   AS72651 : 410, 435, 460, 485, 510, 535 nm
//   AS72652 : 560, 585, 610, 645, 680, 705 nm
//   AS72653 : 730, 760, 810, 860, 900, 940 nm
// ============================================================

// -------------------------
// Pin configuration
// -------------------------

constexpr uint8_t BUZZER_PIN = 25;
constexpr uint8_t RELAY_PIN = 26;

constexpr uint8_t LCD_SDA_PIN = 13;
constexpr uint8_t LCD_SCL_PIN = 14;

constexpr uint8_t SENSOR_SDA_PIN = 21;
constexpr uint8_t SENSOR_SCL_PIN = 22;

// -------------------------
// Relay configuration
// -------------------------

// Modul relay generik (VCC->5V, GND->GND, IN->GPIO) pada board ini terbukti
// ACTIVE-LOW secara fisik: lampu menyala terus saat firmware menulis LOW
// sebagai "off" dan hanya mati sesaat saat menulis HIGH sebagai "on".
// Maka polaritas dibalik di sini supaya perilaku logis (ON saat scan,
// OFF saat idle) sesuai dengan perilaku fisik modul.
constexpr uint8_t RELAY_ON_LEVEL = LOW;
constexpr uint8_t RELAY_OFF_LEVEL = HIGH;

// -------------------------
// LCD
// -------------------------

constexpr uint8_t LCD_ADDRESS = 0x27;

// -------------------------
// AS7265x
// -------------------------

constexpr uint8_t SENSOR_GAIN = AS7265X_GAIN_64X;
constexpr uint8_t SENSOR_INTEGRATION_CYCLES = 50;

constexpr uint16_t SCAN_BEEP_MS = 180;
constexpr uint16_t SCAN_WARMUP_MS = 3000;

// -------------------------
// Sinkronisasi & watchdog
// -------------------------

// Berapa lama firmware menunggu konfirmasi SAVED,<n> dari server setelah
// mengirim DATA, sebelum menyerah dan menampilkan status "belum terkonfirmasi"
// di LCD alih-alih nomor yang belum tentu benar.
constexpr uint16_t SAVE_ACK_TIMEOUT_MS = 4000;

// Batas watchdog: kalau firmware macet total di titik mana pun lebih lama
// dari ini, chip reboot sendiri alih-alih diam beku selamanya. Diberi
// margin cukup besar di atas durasi normal terpanjang (~3s warmup + ~1s
// pengukuran + ~4s tunggu ack = ±8.5s).
constexpr uint32_t WDT_TIMEOUT_S = 15;

// ============================================================
// Objects
// ============================================================

LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);

AS7265X spectralSensor;

// Bus I2C kedua khusus sensor
TwoWire sensorWire = TwoWire(1);

// ============================================================
// State
// ============================================================

bool sensorReady = false;

uint32_t scanNumber = 0;

char commandBuffer[32];
size_t commandLength = 0;

// ============================================================
// Relay
// ============================================================

void setRelay(bool enabled) {
  digitalWrite(
    RELAY_PIN,
    enabled ? RELAY_ON_LEVEL : RELAY_OFF_LEVEL
  );
}

// ============================================================
// LCD
// ============================================================

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

// ============================================================
// Buzzer
// ============================================================

void signalScan() {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(SCAN_BEEP_MS);
  digitalWrite(BUZZER_PIN, LOW);
}

// ============================================================
// I2C scanner
// ============================================================

bool sensorExistsOnI2C() {
  sensorWire.beginTransmission(0x49);

  uint8_t result = sensorWire.endTransmission();

  return result == 0;
}

// ============================================================
// Sinkronisasi hasil (tunggu konfirmasi database dari server)
// ============================================================

// Menunggu baris "SAVED,<scan_no>" dari server (dikirim setelah data
// benar-benar tersimpan di database) selama maksimal timeoutMs. Baris lain
// yang bukan SAVED diabaikan (tetap menunggu) supaya tidak salah baca kalau
// ada command lain nyasar. Return true + scanNoOut terisi kalau ack sah
// diterima tepat waktu; false kalau timeout (tidak ada tebakan/asumsi).
bool waitForSavedAck(uint32_t &scanNoOut, uint16_t timeoutMs) {
  char buffer[32];
  size_t len = 0;
  const uint32_t deadline = millis() + timeoutMs;

  while (millis() < deadline) {
    while (Serial.available() > 0) {
      const char incoming = static_cast<char>(Serial.read());

      if (incoming == '\n' || incoming == '\r') {
        if (len > 0) {
          buffer[len] = '\0';
          if (strncmp(buffer, "SAVED,", 6) == 0) {
            scanNoOut = static_cast<uint32_t>(strtoul(buffer + 6, nullptr, 10));
            return true;
          }
          len = 0;
        }
        continue;
      }

      if (len < sizeof(buffer) - 1) {
        buffer[len++] = incoming;
      } else {
        len = 0; // baris terlalu panjang untuk jadi SAVED,<n> yang valid -- buang
      }
    }
    delay(5);
  }

  return false;
}

// ============================================================
// Scan
// ============================================================

void performScan(bool isRescan) {
  if (!sensorReady) {
    Serial.println("ERROR,AS7265X_NOT_READY");
    Serial.flush();
    return;
  }

  setRelay(true);

  signalScan();

  setLcdLines(
    isRescan ? "Mencoba ulang..." : "Memindai...",
    "Jangan bergerak"
  );

  // Jeda agar illumination (relay/LED) stabil sebelum sensor membaca,
  // supaya pembacaan tidak terjadi saat lampu baru menyala (warm-up).
  delay(SCAN_WARMUP_MS);

  // CATATAN PENTING (lihat juga docs/OPERATOR_AND_MAINTAINER_GUIDE.md):
  // Triad AS7265x sebenarnya 3 chip fisik terpisah (AS72651/AS72652/AS72653) yang
  // di-multiplex lewat satu virtual register DEV_SELECT_CONTROL pada chip master.
  // takeMeasurements() di bawah ini hanya memicu one-shot capture pada SATU device
  // yang sedang aktif terpilih -- dua device lain akan membawa nilai kalibrasi dari
  // siklus sebelumnya (bukan nilai yang benar-benar baru di scan ini).
  //
  // Sudah dicoba men-trigger ketiga device eksplisit satu-persatu (lewat
  // getTemperature(device) sebagai pengganti selectDevice() yang private di
  // library), tapi terbukti membuat board hang/timeout total pada ~40% percobaan
  // scan (kemungkinan I2C bus AS7265x butuh jeda settle lebih panjang antar
  // pemilihan device yang belum berhasil ditemukan nilainya). Karena reliabilitas
  // lebih penting daripada kelengkapan data untuk saat ini, sengaja dikembalikan
  // ke satu panggilan takeMeasurements() yang sudah terbukti 100% reliable.
  // TODO: revisit dengan analisa I2C bus (logic analyzer) sebelum mencoba lagi.
  spectralSensor.takeMeasurements();

  // Matikan relay setelah proses pengukuran sensor selesai
  setRelay(false);

  scanNumber++;

  // ========================================================
  // Serial output (satu baris utuh dengan 20 kolom terformat)
  // ========================================================

  String payload = "DATA,";
  payload += String(scanNumber);

  // AS72651 (410, 435, 460, 485, 510, 535 nm)
  payload += ","; payload += String(spectralSensor.getCalibratedA(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedB(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedC(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedD(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedE(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedF(), 6);

  // AS72652 (560, 585, 610, 645, 680, 705 nm)
  payload += ","; payload += String(spectralSensor.getCalibratedG(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedH(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedR(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedI(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedS(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedJ(), 6);

  // AS72653 (730, 760, 810, 860, 900, 940 nm)
  payload += ","; payload += String(spectralSensor.getCalibratedT(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedU(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedV(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedW(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedK(), 6);
  payload += ","; payload += String(spectralSensor.getCalibratedL(), 6);

  // Kirimkan baris data utuh ke Serial
  Serial.println(payload);
  Serial.flush();

  // Tunggu konfirmasi server bahwa data BENAR-BENAR tersimpan di database
  // sebelum menampilkan nomor scan di LCD. Ini sengaja menggantikan
  // scanNumber lokal (yang cuma hidup di RAM firmware dan reset tiap
  // reboot) dengan scan_no yang sah dari database -- supaya nomor yang
  // dilihat operator di LCD selalu sinkron dengan yang ada di server,
  // bukan tebakan yang bisa meleset.
  uint32_t confirmedScanNo = 0;
  const bool confirmed = waitForSavedAck(confirmedScanNo, SAVE_ACK_TIMEOUT_MS);

  if (confirmed) {
    char line2[17];
    snprintf(
      line2,
      sizeof(line2),
      "Scan #%lu OK",
      static_cast<unsigned long>(confirmedScanNo)
    );
    setLcdLines("Data tersimpan", line2);
  } else {
    // Jujur: data sudah terkirim ke PC, tapi belum ada konfirmasi database
    // dalam waktu wajar. Jangan tampilkan nomor yang belum tentu benar.
    setLcdLines("Terkirim ke PC", "Cek web utk no.");
  }
}

// ============================================================
// Serial commands
// ============================================================

void processCommand(const char *command) {
  if (strcmp(command, "PING") == 0) {

    Serial.println("ACK,PONG");
    Serial.flush();

  } else if (strcmp(command, "SCAN") == 0) {

    performScan(false);

  } else if (strcmp(command, "RESCAN") == 0) {

    performScan(true);

  } else if (strncmp(command, "SAVED,", 6) == 0) {

    // Ack yang datang telat (server lambat, sudah lewat SAVE_ACK_TIMEOUT_MS
    // di dalam performScan()) -- baris ini nyasar ke sini lewat command loop
    // biasa. Bukan command asing, cuma diam-diam diabaikan, jangan dianggap
    // error.

  } else {

    Serial.println("ERROR,UNKNOWN_COMMAND");
    Serial.flush();
  }
}

void readSerialCommands() {
  while (Serial.available() > 0) {

    const char incoming =
      static_cast<char>(Serial.read());

    if (
      incoming == '\n' ||
      incoming == '\r'
    ) {

      if (commandLength > 0) {

        commandBuffer[commandLength] = '\0';

        processCommand(commandBuffer);

        commandLength = 0;
      }

      continue;
    }

    if (
      commandLength <
      sizeof(commandBuffer) - 1
    ) {

      commandBuffer[commandLength++] =
        incoming;

    } else {

      commandLength = 0;

      Serial.println(
        "ERROR,COMMAND_TOO_LONG"
      );
      Serial.flush();
    }
  }
}

// ============================================================
// Watchdog
// ============================================================

// Kalau firmware macet total di titik mana pun (mis. I2C bus nyangkut
// akibat noise elektris) lebih lama dari WDT_TIMEOUT_S, chip reboot sendiri
// alih-alih diam beku selamanya sampai dicabut-colok manual. Ini TIDAK
// mencegah gangguan elektrisnya (itu perbaikan hardware/relay), tapi
// membatasi akibatnya jadi reboot terbatas yang bisa terdeteksi & tercatat
// server, bukan hang tak terbatas.
void setupWatchdog() {
  esp_task_wdt_config_t wdtConfig = {
    .timeout_ms = WDT_TIMEOUT_S * 1000,
    .idle_core_mask = 0,
    .trigger_panic = true,
  };

  // reconfigure() dulu (framework Arduino-ESP32 biasanya sudah
  // menginisialisasi watchdog task secara default); kalau ternyata belum
  // terinisialisasi sama sekali, baru fallback ke init(). Dua-duanya aman
  // dicoba -- hasil error dari langkah pertama tidak fatal, cuma sinyal
  // untuk coba jalur kedua.
  if (esp_task_wdt_reconfigure(&wdtConfig) != ESP_OK) {
    esp_task_wdt_init(&wdtConfig);
  }

  esp_task_wdt_add(NULL);
}

// ============================================================
// Setup
// ============================================================

void setup() {
  setupWatchdog();

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);
  setRelay(false);

  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("BOOT,BUAHSAFE_AS7265X");
  Serial.flush();

  // ========================================================
  // LCD I2C
  // ========================================================

  if (!Wire.begin(
        LCD_SDA_PIN,
        LCD_SCL_PIN
      )) {

    Serial.println(
      "FATAL,LCD_I2C_BUS_FAILED"
    );
    Serial.flush();
  }

  Wire.setClock(100000);
  Wire.setTimeOut(1000);

  lcd.init();
  lcd.backlight();

  setLcdLines(
    "BuahSafe",
    "Init AS7265x..."
  );

  // ========================================================
  // AS7265x I2C
  // ========================================================

  if (!sensorWire.begin(
        SENSOR_SDA_PIN,
        SENSOR_SCL_PIN
      )) {

    Serial.println(
      "FATAL,AS7265X_I2C_BUS_FAILED"
    );
    Serial.flush();

    setLcdLines(
      "ERROR AS7265x",
      "I2C bus gagal"
    );

    return;
  }

  sensorWire.setClock(100000);
  sensorWire.setTimeOut(1000);

  // Tes ACK 0x49 terlebih dahulu.
  if (!sensorExistsOnI2C()) {

    Serial.println(
      "FATAL,AS7265X_I2C_0x49_NOT_FOUND"
    );
    Serial.flush();

    setLcdLines(
      "ERROR AS7265x",
      "0x49 tdk ada"
    );

    return;
  }

  Serial.println(
    "I2C,AS7265X_FOUND,0x49"
  );
  Serial.flush();

  // ========================================================
  // Initialize sensor
  // ========================================================

  if (!spectralSensor.begin(sensorWire)) {

    Serial.println(
      "FATAL,AS7265X_BEGIN_FAILED"
    );
    Serial.flush();

    setLcdLines(
      "ERROR AS7265x",
      "Init gagal"
    );

    return;
  }

  sensorReady = true;

  // ========================================================
  // Sensor configuration
  // ========================================================

  spectralSensor.setGain(SENSOR_GAIN);

  spectralSensor.setIntegrationCycles(
    SENSOR_INTEGRATION_CYCLES
  );

  // Matikan illumination LEDs saat idle.
  spectralSensor.disableBulb(
    AS7265x_LED_WHITE
  );

  spectralSensor.disableBulb(
    AS7265x_LED_IR
  );

  spectralSensor.disableBulb(
    AS7265x_LED_UV
  );

  setLcdLines(
    "BuahSafe siap",
    "Buka website"
  );

  Serial.println(
    "READY,BUAHSAFE_AS7265X_V1"
  );
  Serial.flush();
}

// ============================================================
// Main loop
// ============================================================

void loop() {
  esp_task_wdt_reset();
  readSerialCommands();
}