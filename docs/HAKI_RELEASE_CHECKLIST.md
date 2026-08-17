---
status: active-checklist
last_verified: 2026-08-17
audience: authorized-maintainers
sensitivity: restricted
---

# HAKI Release Checklist

## Identity and ownership

- [ ] Final program title approved.
- [ ] All creators and their contributions confirmed.
- [ ] Rights holder/applicant confirmed.
- [ ] Transfer, institution, UMKM, or authority documents identified if applicable.
- [ ] First announcement/publication date, city, and country confirmed.
- [ ] Third-party dependency and contribution history reviewed.

## Source freeze

- [ ] Clean release commit created.
- [ ] Release version/tag recorded.
- [ ] `git status` clean except explicitly excluded local data.
- [x] Automated tests pass. — 53/53, 2026-08-17. See `TEST_RESULTS_2026-08-17.md`.
- [ ] Source snapshot excludes `.venv`, SQLite data, cache, device logs, and temporary files.
- [ ] Snapshot and key documents have SHA-256 hashes.

## Program evidence

- [x] One-paragraph and full program descriptions. — `ARCHITECTURE.md`.
- [x] Architecture/data-flow diagram. — `ARCHITECTURE.md` (component diagram + scan-retry sequence diagram).
- [x] Feature inventory. — `ARCHITECTURE.md` component/layer breakdown covers this; a standalone bullet list can be split out if the DJKI form requires a separate document.
- [x] Installation and operating guide. — `README.md` + `OPERATOR_AND_MAINTAINER_GUIDE.md`.
- [x] Serial protocol and database schema summary. — `OPERATOR_AND_MAINTAINER_GUIDE.md` "Hardware and serial contract" + "Data contract" sections.
- [ ] Synthetic-data screenshots of disconnected, connected, scan, history, label, debug, and CSV flow. — real (non-synthetic) screenshots of connected/scan/history/label flow were captured during 2026-08-17 browser E2E testing but not archived as files; needs a dedicated pass with either synthetic sample data or explicit permission to use real captured data.
- [x] Test result record. — `TEST_RESULTS_2026-08-17.md` (automated + manual E2E + firmware fix verification).
- [ ] Physical demonstration evidence, or an explicit note that hardware validation is separate. — note added in `OPERATOR_AND_MAINTAINER_GUIDE.md` Known limitations ("No physical enclosure/lighting standardization proven by source"); actual photo/video evidence not yet captured.
- [x] Known limitations and claim boundaries. — `OPERATOR_AND_MAINTAINER_GUIDE.md` "Known limitations and claim boundaries" section, dated 2026-08-17.

## Portal preparation

- [ ] Current DJKI requirements and upload formats rechecked on the submission date.
- [ ] Required identity and statement documents ready.
- [ ] Example of work prepared in the accepted format/size.
- [ ] Applicant account access confirmed by its human owner.
- [ ] Billing/payment and final submission performed by an authorized human.
- [ ] Receipt, application number, uploaded package hash, and final letter archived securely.
