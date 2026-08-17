---
status: verified-guide
last_verified: 2026-08-15
audience: human-and-ai
sensitivity: restricted
evidence_basis:
  - ../README.md
  - 2026-08-02-web-capture-design.md
  - ../app.py
  - ../database.py
  - ../serial_device.py
  - ../buahsafe.ino
---

# Operator and Maintainer Guide

## System purpose

BuahSafe Web Capture is a local data-acquisition application. It sends `PING` and `SCAN` commands to an ESP32, parses one calibrated 18-channel AS7265x response, stores the successful measurement in SQLite, and exposes history, labeling, debug information, and CSV export through a Flask web interface.

It is not yet a production guava-quality classifier. The application currently records evidence needed to build that classifier.

## Component map

| Component | Responsibility |
| --- | --- |
| `buahsafe.ino` | ESP32 firmware, two I2C buses, AS7265x configuration, relay, LCD, buzzer, serial protocol. |
| `serial_device.py` | COM discovery, connect/handshake, timeout/error behavior, frame parsing, in-memory debug log. |
| `database.py` | SQLite schema, legacy 6-channel migration, insert/list/label/export source rows. |
| `app.py` | Local Flask UI and JSON/CSV endpoints. |
| `templates/` and `static/` | Browser interface. |
| `tests/` | Parser, database, serial-device, and application behavior. |

## Hardware and serial contract

- Baud: 115200.
- Commands: `PING` and `SCAN`, newline terminated.
- Handshake response: `ACK,PONG`.
- Data response: `DATA,<scan_no>,<18 finite values>`.
- Firmware timeout expectations: connection handshake up to 8 seconds; scan up to 15 seconds.
- LCD bus: SDA GPIO13, SCL GPIO14, address `0x27`.
- AS7265x bus: SDA GPIO21, SCL GPIO22, address `0x49`.
- Buzzer: GPIO25.
- Relay: GPIO26; source currently defines `HIGH` as on and `LOW` as off. Confirm against the physical relay module before energizing illumination.

All devices must share ground. The physical power, relay contacts, lamp type, and enclosure are not proven by source code and require human confirmation.

## Data contract

Each row contains:

- local laptop timestamp;
- validated uppercase `fruit_id`;
- firmware scan number;
- `nm410` through `nm940` for 18 wavelengths;
- label: empty, `bagus`, or `rusak`.

The application writes only after a successful parsed scan. The dashboard supports deleting individual rows or a selected batch from the records table (single confirmation dialog required); there is still no bulk "wipe all data" shortcut, so accidental mass deletion requires selecting rows explicitly. Local database files under `data/` are ignored by Git and must be backed up separately — export CSV regularly since deletion is permanent (no undo, no soft-delete/trash).

## Safe operating procedure

1. Inspect wiring and confirm relay/lamp safety with power disconnected.
2. Upload the firmware and record the commit/version.
3. Close Arduino Serial Monitor so Flask can exclusively own the COM port.
4. Start the application through `run_buahsafe.bat` or `launch.py`.
5. Select the correct COM port and connect; confirm the handshake.
6. Enter a unique ID for one physical fruit.
7. Place the fruit at a documented position and keep light, distance, and chamber conditions constant.
8. Trigger one scan; confirm 18 values, one new row, and no error log.
9. Repeat for planned orientations while keeping the same `fruit_id`.
10. Export CSV and back up both CSV and SQLite data with session metadata.
11. Assign a ground-truth label only after the labeling procedure is complete.

## Development commands

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe launch.py
```

The physical scan test is separate from automated tests and cannot be replaced by mocks.

Local result on 2026-08-15: all 25 `unittest` tests passed in an ignored virtual environment. `pytest` is not declared in `requirements.txt`; use the standard-library runner above unless the dependency contract is intentionally changed.

## Failure guide

| Symptom | First checks |
| --- | --- |
| No COM port | USB cable/data capability, driver, Windows Device Manager, board power. |
| Access denied | Close Serial Monitor/Plotter and other BuahSafe instances. |
| Handshake timeout | Correct port, firmware uploaded, baud 115200, board reset output. |
| `AS7265X_NOT_READY` | Sensor power/ground, I2C address 0x49, SDA/SCL pins, library compatibility. |
| Wrong field count | Firmware/software version mismatch or partial serial line. Preserve raw line. |
| Non-finite value | Sensor/firmware fault; do not insert a substitute value. |
| Missing database row | Confirm scan returned success; inspect `/api/debug`; do not fabricate data. |

## Change rules

- Keep firmware and parser wavelength order identical.
- Add a migration before changing the SQLite schema.
- Never silently coerce malformed sensor frames into zeros.
- Keep local-only binding (`127.0.0.1`) unless an explicit authentication/network design is added.
- Add tests for parser, API, migration, and failure behavior before changing the protocol.

## Definition of done

A change is complete when automated tests pass, the application starts, relevant failure states remain controlled, and—if hardware behavior changed—a physical scan is recorded with the exact firmware/software commit.
