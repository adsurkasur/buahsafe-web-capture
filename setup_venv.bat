@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  echo Virtual environment sudah ada di .venv
  goto :install
)

echo Membuat virtual environment di .venv ...
py -m venv .venv
if errorlevel 1 (
  echo Gagal membuat virtual environment. Pastikan Python sudah terpasang dan ada di PATH.
  pause
  exit /b 1
)

:install
echo Menginstal dependencies dari requirements.txt ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Gagal menginstal dependencies.
  pause
  exit /b 1
)

echo.
echo Selesai. Jalankan run_buahsafe.bat untuk memulai aplikasi.
pause

endlocal
