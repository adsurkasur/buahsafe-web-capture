#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SparkFun_AS7265X.h>

// ============================================================
// BuahSafe - firmware akuisisi dataset manual AS7265x
//
// Serial command:
//   PING
//     -> ACK,PONG
//
//   SCAN
//     -> DATA,<scan>,
//        <410>,<435>,<460>,<485>,<510>,<535>,
//        <560>,<585>,<610>,<645>,<680>,<705>,
//        <730>,<760>,<810>,<860>,<900>,<940>
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

constexpr uint8_t RELAY_ON_LEVEL = HIGH;
constexpr uint8_t RELAY_OFF_LEVEL = LOW;

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
// Scan
// ============================================================

void performScan() {
  if (!sensorReady) {
    Serial.println("ERROR,AS7265X_NOT_READY");
    Serial.flush();
    return;
  }

  setRelay(true);

  signalScan();

  setLcdLines(
    "Memindai...",
    "Jangan digerak"
  );

  // Mengambil measurement baru dari ketiga sensor (AS72651, AS72652, AS72653).
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

  char line2[17];
  snprintf(
    line2,
    sizeof(line2),
    "Scan #%lu OK",
    static_cast<unsigned long>(scanNumber)
  );

  setLcdLines(
    "Data terkirim",
    line2
  );
}

// ============================================================
// Serial commands
// ============================================================

void processCommand(const char *command) {
  if (strcmp(command, "PING") == 0) {

    Serial.println("ACK,PONG");
    Serial.flush();

  } else if (strcmp(command, "SCAN") == 0) {

    performScan();

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
// Setup
// ============================================================

void setup() {
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
  readSerialCommands();
}