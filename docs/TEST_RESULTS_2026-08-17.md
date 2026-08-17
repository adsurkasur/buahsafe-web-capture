---
status: archived-record
recorded: 2026-08-17
audience: human-and-ai
sensitivity: restricted
purpose: HAKI evidence - test result record
---

# Test Result Record — 2026-08-17

## Automated tests

```
Command: .\.venv\Scripts\python.exe -m unittest discover -s tests -v
Result:  Ran 53 tests in 1.225s — OK
```

Covers: DATA-line parsing (valid/invalid field counts, non-finite values,
noise-prefixed lines), database (insert, scan_no autoincrement semantics,
scan_no never reused after delete, reset-all), serial device (handshake,
scan retry with SCAN/RESCAN command selection, timeout recovery, reboot
detection, SAVED-ack notification), and Flask API behavior (connect, scan
success/failure flow including automatic retry, label update, delete
single/all, reset endpoint).

## End-to-end manual test (real hardware, this machine, COM3)

Performed through the actual browser UI (not just the API) unless noted:

1. Connect to ESP32 via port dropdown + "Hubungkan ESP32" — handshake
   succeeded (`ACK,PONG`).
2. Three scans with distinct `fruit_id` values (`E2E_JAMBU_A/B/C`) via the
   "Ambil satu scan" button:
   - Scan A: succeeded on first attempt.
   - Scan B: succeeded on first attempt.
   - Scan C: first attempt failed (automatic retry UI shown: "Masih
     mencoba di balik layar..."), second/third attempt recovered a clean
     18-channel reading. Row saved correctly with the retry-recovered data.
3. Labeling: set scan A to `bagus`, scan B to `rusak` via the API
   (`PATCH /api/measurements/<id>/label`) — confirmed via re-query.
4. Search: `?search=E2E_JAMBU_C` returned exactly the matching row.
5. Filter: `?label=bagus` / `?label=rusak` each returned exactly the
   correctly-labeled row.
6. Delete single row: removed scan C, confirmed via CSV re-export.
7. CSV export (`/export.csv`): header and all rows matched the database
   exactly, including the applied labels, at every step above.
8. Reset Database: cleared all rows via the UI confirm dialog, verified
   `total_scans: 0` and an empty table afterward.

Result: full acquisition → label → filter/search → export → reset cycle
verified working end-to-end with real hardware.

## Firmware fix verification (raw serial, bypassing the Flask layer)

To confirm the 2026-08-17 firmware fix (SCAN command loss during the
SAVED-ack wait window) independently of any server-side retry masking it:

- 12–15 back-to-back `SCAN` commands sent directly over the serial port
  with **zero** artificial delay between them (harder than real operator
  usage, where there is always at least human reaction time between scans).
- Result: 0 lost commands / 0 unexplained full-timeout responses across all
  runs, versus 0/5 first-attempt success reproducibly before the fix.
- The separate, still-open intermittent single-byte corruption on the
  460 nm channel (see Known limitations in
  [`OPERATOR_AND_MAINTAINER_GUIDE.md`](OPERATOR_AND_MAINTAINER_GUIDE.md))
  was still observed at roughly the same rate in this same test, confirming
  it is a distinct issue from the command-loss bug and not resolved by this
  fix.

## Not covered by this record

- No logic-analyzer/oscilloscope capture of the UART line exists yet for
  the open 460 nm corruption issue.
- No test has been performed on the laptop referenced in the "laptop vs.
  desktop reliability gap" limitation; that machine failed even the
  connection handshake and was not used for any of the above.
- Physical demonstration evidence (photos/video of the physical scanning
  setup, enclosure, and a real guava sample) is separate from this
  software test record and has not been captured here.

## Addendum — 2026-08-17 (flowchart-alignment UI changes + label rename)

Later the same day, the application was adjusted to align with an
independently-produced flowchart (`Flowchart 2 BuahSafe.drawio.pdf`):
explicit guard messages for the ID-jambu input (empty / invalid characters /
accepted), a contextual retry button in the error inspector (retries the
action that actually failed — connect vs. scan — instead of always
retrying scan), and a label-vocabulary rename from `bagus`/`rusak` to
`normal`/`anomali` across the backend, frontend, and this documentation set.

```
Command: python3 -m unittest discover -s tests -v
Result:  Ran 54 tests in 1.075s — OK
```

The one additional test (54 vs. the 53 above) covers the new
`_migrate_label_values()` step in `database.py`: legacy rows still labeled
`bagus`/`rusak` are rewritten to `normal`/`anomali` on `initialize()`, and
running `initialize()` multiple times is confirmed idempotent (no further
changes after the first migration). No existing spectral data, `scan_no`,
or `fruit_id` values are touched by this migration — only the `label` text
column.

Not covered by this addendum: a fresh physical hardware scan was not
re-run after this change, since it touches only label text and
client-side guard messaging, not the serial protocol, parser, or database
insert path exercised by the 2026-08-17 hardware test above.
