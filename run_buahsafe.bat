@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment belum tersedia.
  echo Jalankan setup terlebih dahulu sesuai README.md.
  pause
  exit /b 1
)

echo Menjalankan BuahSafe Web Capture...
echo Buka http://127.0.0.1:5000 jika browser tidak terbuka otomatis.
".venv\Scripts\python.exe" launch.py

endlocal
