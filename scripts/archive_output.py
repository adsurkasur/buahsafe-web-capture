"""Archive obsolete output material without deleting data or changing active inputs.

Default is a dry run. --apply moves only the listed paths inside output.
--verify rechecks archive hashes and the two preserved dataset inputs.
Only the Python standard library is used; hashing streams one MiB at a time.
"""
from pathlib import Path
from datetime import datetime
import argparse, hashlib, json, os, shutil

APP=Path(__file__).resolve().parents[1]
OUTPUT=(APP/'output').resolve()
ARCHIVE=OUTPUT/'arsip/2026-10-30-cleanup'
MOVES=[
    ('data_analysis','Analisis serta grafik historis; tidak digunakan evaluasi646.'),
    ('venv','Lingkungan konversi lama; aplikasi dan evaluasi terbaru memakai .venv di root aplikasi.'),
    ('convert_csv.bat','Konverter CSV historis beserta lingkungan lamanya.'),
    ('buahsafe_dataset_06102026.csv','Batch mentah Oktober yang telah tercakup pada workbook terbaru.'),
    ('buahsafe_dataset_06102026.xlsx','Salinan spreadsheet batch mentah Oktober.'),
    ('scan ade.csv','Berkas percobaan awal, bukan sumber model terbaru.'),
    ('scan ade.xlsx','Salinan spreadsheet percobaan awal.'),
    ('fixed/clean_labels.py','Normalisasi batch lama; input yang dirujuk sudah berada dalam arsip.'),
    ('finalised/finalise_dataset.py','Skrip pembentukan dataset518; bukan pembentuk workbook646 terbaru.'),
]
KEEP=['fixed/buahsafe_dataset_latest.xlsx','finalised/buahsafe_dataset_gabungan_final.csv']
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def inventory(path):
    if path.is_file():return {'kind':'file','files':1,'bytes':path.stat().st_size,'sha256':sha(path)}
    digest=hashlib.sha256();count=0;size=0
    for folder,dirs,files in os.walk(path,followlinks=False):
        dirs.sort()
        for name in sorted(files):
            item=Path(folder)/name
            if item.is_symlink():raise RuntimeError('Unexpected symbolic link: '+str(item))
            rel=item.relative_to(path).as_posix();filehash=sha(item)
            digest.update((rel+'\0'+filehash+'\n').encode('utf8'));count+=1;size+=item.stat().st_size
    return {'kind':'directory','files':count,'bytes':size,'tree_sha256':digest.hexdigest()}
def inside(path):
    resolved=path.resolve()
    assert resolved!=OUTPUT and resolved.is_relative_to(OUTPUT),str(resolved)
    return resolved
def verify():
    m=json.loads((ARCHIVE/'MANIFEST.json').read_text(encoding='utf8'))
    for item in m['moves']:
        dst=inside(OUTPUT/item['archive'])
        assert dst.exists() and inventory(dst)==item['before'],str(dst)
        assert not (OUTPUT/item['source']).exists(),item['source']
    for name,snapshot in m['preserved'].items():assert inventory(inside(OUTPUT/name))==snapshot,name
    assert sorted(p.name for p in OUTPUT.iterdir())==['README.md','arsip','finalised','fixed']
    assert sorted(p.name for p in (OUTPUT/'fixed').iterdir())==['buahsafe_dataset_latest.xlsx']
    assert sorted(p.name for p in (OUTPUT/'finalised').iterdir())==['buahsafe_dataset_gabungan_final.csv']
    print('PASS:9 moved roots; all archived contents match;2 active input hashes unchanged; output layout clean')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--verify',action='store_true');args=ap.parse_args()
    if args.verify:verify();return
    assert not ARCHIVE.exists(),'Archive already exists; use --verify, not another move'
    snapshots={name:inventory(inside(OUTPUT/name)) for name in KEEP}
    planned=[]
    for rel,reason in MOVES:
        src=inside(OUTPUT/rel);dst=inside(ARCHIVE/rel)
        assert src.exists() and not dst.exists(),rel
        planned.append({'source':rel,'archive':dst.relative_to(OUTPUT).as_posix(),'reason':reason,'local_only':rel=='venv','before':inventory(src)})
    print('Archive roots:',len(planned),'files:',sum(i['before']['files'] for i in planned),'MiB:',round(sum(i['before']['bytes'] for i in planned)/1024**2,2))
    for item in planned:print(item['source'],'->',item['archive'])
    if not args.apply:return
    for item in planned:
        src=inside(OUTPUT/item['source']);dst=inside(OUTPUT/item['archive'])
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(src),str(dst))
        assert inventory(dst)==item['before'],str(dst)
    manifest={'date':'2026-10-30','status':'moved-and-hash-verified','scope':str(OUTPUT),'preserved':snapshots,'moves':planned,'deleted_files':0}
    (ARCHIVE/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (ARCHIVE/'README.md').write_text('''# Arsip output 30 Oktober 2026

Berkas pada direktori ini dipindahkan dari folder output karena sudah tidak menjadi sumber pengembangan atau pengujian terbaru. Tidak ada isi yang dihapus. Jalur asal, alasan, jumlah berkas, ukuran, dan hash sebelum pemindahan tercatat pada MANIFEST.json. Setiap hash diperiksa kembali setelah pemindahan.

Folder data_analysis berisi analisis historis dan tetap tersedia untuk menelusuri hasil lama. Batch mentah, percobaan scan, konverter, serta skrip finalisasi518 disimpan dengan jalur asalnya. Lingkungan venv merupakan lingkungan konversi lama yang berisi jalur instalasi terdahulu; lingkungan ini disimpan hanya secara lokal dan dikecualikan dari Git. Lingkungan aplikasi .venv di root repositori tidak dipindahkan.

Verifikasi lokal: jalankan Python pada scripts/archive_output.py --verify dari root repositori aplikasi. Skrip membaca berkas secara bertahap tanpa melatih model atau menjalankan aplikasi.
''',encoding='utf8')
    (OUTPUT/'README.md').write_text('''# Dataset aktif dan arsip BuahSafe

| Lokasi | Peran |
|---|---|
| [fixed/buahsafe_dataset_latest.xlsx](fixed/buahsafe_dataset_latest.xlsx) | Sumber pengukuran terbaru:81buah dan646pemindaian. Workbook asli dipertahankan. |
| [finalised/buahsafe_dataset_gabungan_final.csv](finalised/buahsafe_dataset_gabungan_final.csv) | Dataset518pemindaian yang masih dirujuk simulator, evaluasi lama, pembangkit bahan ML, dan pengujian sandbox. Bukan acuan angka laporan terbaru. |
| [arsip/2026-10-30-cleanup](arsip/2026-10-30-cleanup/README.md) | Analisis lama, batch mentah Oktober, percobaan, konverter, skrip lama, dan lingkungan konversi yang telah dipindahkan. |
| arsip/ | Dataset historis yang sudah diarsipkan sebelumnya, tetap dipertahankan. |

Evaluasi646 menggunakan salinan kerja yang menerapkan dua koreksi ID terdokumentasi; file sumber di atas tidak diubah. Hasil baru tersedia di [folder evaluasi646](../../laporan-akhir/persiapan-revisi-baseline/audit-20261030/ml646/HASIL_ML646.md). Model baru belum diaktifkan pada aplikasi atau server.

Pembersihan ini hanya mengubah penempatan bahan lama. Model aplikasi, database, lingkungan aplikasi .venv, workbook terbaru dan CSV yang masih dirujuk kode tetap utuh. Manifest arsip memungkinkan setiap pemindahan ditelusuri dan dikembalikan.
''',encoding='utf8')
    verify()
if __name__=='__main__':main()
