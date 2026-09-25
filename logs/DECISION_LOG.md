# Decision Log (Architecture Decision Records)

### [DEC-002] Dataset final sebagai sumber tunggal analisis ML
- **Date**: 2026-09-19
- **Status**: Accepted
- **Context**: `fixed/buahsafe_dataset_gabungan_08092026_clean.*` masih berisi 2 scan dengan ID tertukar, format ID campuran, dan `scan_no` dobel (303-310).
- **Decision**: Semua skrip analisis membaca `output/finalised/buahsafe_dataset_gabungan_final.xlsx`, yang dibangun ulang dari data mentah oleh `output/finalised/finalise_dataset.py` (koreksi ID dikunci per timestamp, validasi ketat). File lama dibiarkan apa adanya sebagai arsip.
- **Consequences**: Angka Monev 3 di laporan perlu diperbarui (lihat PENJELASAN_ML_MONEV3.md §8.D). Batch baru cukup ditambahkan ke skrip finalisasi.

### [DEC-001] Adoption of Modular Logging Protocol
- **Date**: 2026-09-16
- **Status**: Accepted
- **Context**: Standardizing change tracking, observability, and auditability across all managed projects for AI agents and human contributors.
- **Decision**: Mandate `logs/ACTIVITY_LOG.md`, `logs/DECISION_LOG.md`, and `logs/CHANGELOG.md` updates across all repositories.
- **Consequences**: Consistent history, reduced context loss during multi-agent handoffs.\n