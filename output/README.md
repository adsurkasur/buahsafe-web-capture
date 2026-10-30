# Dataset aktif dan arsip BuahSafe

| Lokasi | Peran |
|---|---|
| [fixed/buahsafe_dataset_latest.xlsx](fixed/buahsafe_dataset_latest.xlsx) | Sumber pengukuran terbaru:81buah dan646pemindaian. Workbook asli dipertahankan. |
| [finalised/buahsafe_dataset_gabungan_final.csv](finalised/buahsafe_dataset_gabungan_final.csv) | Dataset518pemindaian yang masih dirujuk simulator, evaluasi lama, pembangkit bahan ML, dan pengujian sandbox. Bukan acuan angka laporan terbaru. |
| [arsip/2026-10-30-cleanup](arsip/2026-10-30-cleanup/README.md) | Analisis lama, batch mentah Oktober, percobaan, konverter, skrip lama, dan lingkungan konversi yang telah dipindahkan. |
| arsip/ | Dataset historis yang sudah diarsipkan sebelumnya, tetap dipertahankan. |

Evaluasi646 menggunakan salinan kerja yang menerapkan dua koreksi ID terdokumentasi; file sumber di atas tidak diubah. Hasil baru tersedia di [folder evaluasi646](../../laporan-akhir/persiapan-revisi-baseline/audit-20261030/ml646/HASIL_ML646.md). Model baru belum diaktifkan pada aplikasi atau server.

Pembersihan ini hanya mengubah penempatan bahan lama. Model aplikasi, database, lingkungan aplikasi .venv, workbook terbaru dan CSV yang masih dirujuk kode tetap utuh. Manifest arsip memungkinkan setiap pemindahan ditelusuri dan dikembalikan.
