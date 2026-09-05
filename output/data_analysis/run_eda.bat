@echo off
setlocal enabledelayedexpansion
title BuahSafe - EDA Spectral Runner
cd /d "%~dp0"

echo ============================================================
echo        BUAHSAFE: VIRTUAL ENVIRONMENT AND EDA RUNNER
echo ============================================================
echo.

set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

:: 1. Cek VENV lokal atau parent
if exist "%VENV_PY%" goto :VENV_FOUND

if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "VENV_PY=%~dp0..\.venv\Scripts\python.exe"
    goto :VENV_FOUND
)
if exist "%~dp0..\..\.venv\Scripts\python.exe" (
    set "VENV_PY=%~dp0..\..\.venv\Scripts\python.exe"
    goto :VENV_FOUND
)

:: 2. Buat VENV baru jika belum ada
echo [WARNING] Virtual environment tidak ditemukan.
echo [INFO] Menyiapkan pembuatan .venv baru di direktori ini...

set "BASE_PY="
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "BASE_PY=py -3"
    goto :DO_CREATE
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "BASE_PY=python"
    goto :DO_CREATE
)

for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python310\python.exe"
) do (
    if exist %%p (
        set "BASE_PY=%%p"
        goto :DO_CREATE
    )
)

echo [ERROR] Base Python tidak ditemukan di sistem Windows.
goto :END

:DO_CREATE
echo [INFO] Membuat .venv menggunakan base Python: %BASE_PY%
%BASE_PY% -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo [ERROR] Gagal membuat virtual environment.
    goto :END
)
echo [OK] Virtual environment berhasil dibuat.
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

:VENV_FOUND
echo [OK] Menggunakan Python VENV: "%VENV_PY%"
echo [INFO] Memeriksa dependencies di dalam venv...

"%VENV_PY%" -c "import pandas, openpyxl, matplotlib, seaborn, scipy, sklearn" >nul 2>&1
if %errorlevel% equ 0 goto :RUN_SCRIPT

echo [INFO] Menginstal modul ke dalam venv: pandas, openpyxl, matplotlib, seaborn, scipy, scikit-learn...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install pandas openpyxl matplotlib seaborn scipy scikit-learn
if %errorlevel% neq 0 (
    echo [ERROR] Gagal menginstal dependencies.
    goto :END
)

:RUN_SCRIPT
echo [OK] Semua dependencies siap.
echo.
echo [INFO] Menjalankan eda.py...
echo ============================================================
"%VENV_PY%" eda.py

:END
echo.
echo ============================================================
pause