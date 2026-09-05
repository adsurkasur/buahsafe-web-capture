@echo off
setlocal

:: 1. Cek perintah Python (py atau python)
set "PY_CMD="
py --version >nul 2>&1 && set "PY_CMD=py"
if not defined PY_CMD (
    python --version >nul 2>&1 && set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [ERROR] Python tidak terdeteksi di sistem.
    pause
    exit /b
)

:: 2. Buat virtual environment jika belum ada
if not exist "venv" (
    echo [INFO] Membuat virtual environment 'venv'...
    %PY_CMD% -m venv venv
)

set "PYTHON_EXEC=venv\Scripts\python.exe"

:: 3. Cek dan instal modul pandas & openpyxl jika belum terpasang
%PYTHON_EXEC% -c "import pandas, openpyxl" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Menginstal modul pandas dan openpyxl di venv...
    venv\Scripts\pip.exe install pandas openpyxl
)

:: 4. Eksekusi konversi langsung dalam satu baris perintah
echo [INFO] Menjalankan konversi CSV ke XLSX...
%PYTHON_EXEC% -c "import glob, os, pandas as pd; files = glob.glob('*.csv'); print(f'Ditemukan {len(files)} file CSV.') if files else print('Tidak ada file CSV.'); [(print(f' - Memproses: {f}'), pd.read_csv(f, encoding_errors='replace').to_excel(os.path.splitext(f)[0] + '.xlsx', index=False)) for f in files]; print('Selesai! Semua file berhasil dikonversi.') if files else None"

echo.
echo Proses selesai.
pause