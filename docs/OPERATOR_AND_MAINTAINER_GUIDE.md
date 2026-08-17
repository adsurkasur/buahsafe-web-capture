---
status: verified-guide
last_verified: 2026-08-17
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

BuahSafe Web Capture is a local data-acquisition application. It sends `PING`/`SCAN`/`RESCAN` commands to an ESP32 (with automatic retry on transient failure), parses one calibrated 18-channel AS7265x response, stores the successful measurement in SQLite, and exposes history, labeling, debug information, and CSV export through a Flask web interface.

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
- Commands (server → firmware), newline terminated:
  - `PING` — handshake probe.
  - `SCAN` — operator-initiated measurement.
  - `RESCAN` — server-initiated retry of a scan that just failed/timed out; functionally identical to `SCAN`, but the firmware shows "Mencoba ulang..." on the LCD instead of "Memindai..." so the operator knows this is an automatic retry, not a fresh request.
  - `SAVED,<scan_no>` — sent by the server immediately after a measurement is durably written to SQLite, so the firmware can show the operator the real database-assigned scan number on the LCD instead of its own volatile RAM counter (which resets on every reboot). The firmware waits up to `SAVE_ACK_TIMEOUT_MS` (4000 ms) for this after sending `DATA,...`; if it doesn't arrive in time the LCD falls back to "Terkirim ke PC / Cek web utk no." — the row is still saved correctly, only the LCD confirmation is delayed/missing.
- Handshake response: `ACK,PONG`.
- Data response: `DATA,<firmware_local_scan_no>,<18 finite values>`. The server does **not** trust `firmware_local_scan_no` for the persisted `scan_no` — see Data contract below.
- Firmware timeout expectations: connection handshake up to 8 seconds; scan response up to 18 seconds (plus up to 5 seconds of grace if a line is actively arriving right at the deadline). The server automatically retries a failed/timed-out scan up to 3 total attempts (1.5 s spacing) before surfacing an error to the operator; attempts 2 and 3 send `RESCAN` instead of `SCAN`.
- LCD bus: SDA GPIO13, SCL GPIO14, address `0x27`.
- AS7265x bus: SDA GPIO21, SCL GPIO22, address `0x49`.
- Buzzer: GPIO25.
- Relay: GPIO26. The physical relay module on the current board is **active-low** (energizes on `LOW`, not `HIGH`) — firmware defines `RELAY_ON_LEVEL = LOW` / `RELAY_OFF_LEVEL = HIGH` to compensate. Re-verify this against the actual relay module before energizing illumination if the module is ever swapped.
- ESP32 Task Watchdog Timer: 15 seconds (`WDT_TIMEOUT_S`). If firmware execution genuinely blocks (e.g. a stuck I2C transaction) longer than this, the chip reboots itself rather than hanging forever. The server detects this via boot/ready signatures left in the serial buffer and logs it as a WARN rather than silently discarding the evidence.

All devices must share ground. The physical power, relay contacts, lamp type, and enclosure are not proven by source code and require human confirmation.

## Data contract

Each row contains:

- local laptop timestamp;
- validated uppercase `fruit_id`;
- `scan_no` — the database's own `AUTOINCREMENT` row id, **not** the value the ESP32 reported. The firmware's own counter lives only in RAM and resets on every reboot, so it cannot be trusted as a stable identifier; the server overwrites it with the SQLite id immediately after insert, guaranteeing it is permanent, gap-free (never reused after a delete), and reboot-proof;
- `nm410` through `nm940` for 18 wavelengths;
- label: empty, `bagus`, or `rusak`.

The application writes only after a successful parsed scan. The dashboard supports deleting individual rows, a selected batch, or **all data at once** via the "Reset Database" button in the records header — this also resets the `scan_no` autoincrement sequence back to 1, so use it only when starting a genuinely new dataset. All destructive actions require confirmation and are permanent (no undo, no soft-delete/trash). Local database files under `data/` are ignored by Git and must be backed up separately — export CSV regularly.

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

Local result on 2026-08-17: all 53 `unittest` tests passed in an ignored virtual environment (`python -m unittest discover -s tests -v`, 1.2s). `pytest` is not declared in `requirements.txt`; use the standard-library runner above unless the dependency contract is intentionally changed.

## Known limitations and claim boundaries

- **Not yet a production guava-quality classifier.** This application records evidence (calibrated 18-channel spectra + operator labels); it does not itself classify fruit quality.
- **Intermittent single-channel byte corruption (open, mitigated).** Observed during 2026-08-17 hardware testing: occasionally (roughly 1 in 4–5 scans in back-to-back testing with the relay physically disconnected) a single stray byte appears mid-transmission in one specific field (the 460 nm channel), producing an unparseable value. Two software hypotheses were tested and ruled out — an Arduino `String` heap-reallocation bug (fixed anyway as a legitimate hardening, did not change the failure rate) and a command-loss bug in the SAVED-ack wait window (real bug, fixed and verified separately, see below). The corruption itself is therefore currently believed to be electrical/timing in origin rather than a software defect, but this has not been confirmed with a logic analyzer or oscilloscope. **It never reaches the database**: `parse_data_line()` rejects any line with a non-finite/unparseable field before it reaches SQLite, and the automatic retry (see below) has recovered a valid reading on every occurrence observed so far. Practical effect: occasional multi-second delay on a scan, never corrupted or fabricated data.
- **Fixed and verified 2026-08-17: SCAN command could be silently lost.** `waitForSavedAck()` previously discarded any serial line that wasn't a `SAVED,<n>` ack while waiting up to 4 seconds for one, including a legitimate next `SCAN` command if it happened to arrive in that window — with no error output, producing a full timeout on the next attempt. Fixed by routing the stray line back through the normal command dispatch instead of discarding it. Verified with 12–15 back-to-back scans at zero artificial delay between them, 0 lost commands (previously reproducible on ~100% of first attempts under the same conditions).
- **Laptop vs. desktop reliability gap (open, hardware-suspected, not software-fixable from here).** The same firmware/ESP32 unit that operates acceptably on the desktop failed to complete even the initial handshake reliably when moved to a different laptop, with much heavier byte corruption. Suspected cause: USB cable/port power delivery differences, not yet confirmed. Until resolved, treat the desktop as the primary data-acquisition machine.
- **No physical enclosure/lighting standardization proven by source.** Consistent lighting, sensor distance, and fruit positioning across scans is an operator procedure (see Safe operating procedure below), not something the software enforces or can verify.

## Failure guide

| Symptom | First checks |
| --- | --- |
| No COM port | USB cable/data capability, driver, Windows Device Manager, board power. |
| Access denied | Close Serial Monitor/Plotter and other BuahSafe instances. |
| Handshake timeout | Correct port, firmware uploaded, baud 115200, board reset output. |
| `AS7265X_NOT_READY` | Sensor power/ground, I2C address 0x49, SDA/SCL pins, library compatibility. |
| Wrong field count | Firmware/software version mismatch or partial serial line. Preserve raw line. |
| Non-finite value / single stray character in one field | Usually the known 460nm intermittent corruption (see Known limitations) — confirm the automatic retry recovered a clean value; if the *same* field corrupts on nearly every scan rather than occasionally, treat as a new issue and preserve the raw line. |
| Non-finite value elsewhere | Sensor/firmware fault; do not insert a substitute value. |
| Missing database row | Confirm scan returned success; inspect `/api/debug`; do not fabricate data. |

## Change rules

- Keep firmware and parser wavelength order identical.
- Add a migration before changing the SQLite schema.
- Never silently coerce malformed sensor frames into zeros.
- Keep local-only binding (`127.0.0.1`) unless an explicit authentication/network design is added.
- Add tests for parser, API, migration, and failure behavior before changing the protocol.

## Definition of done

A change is complete when automated tests pass, the application starts, relevant failure states remain controlled, and—if hardware behavior changed—a physical scan is recorded with the exact firmware/software commit.
