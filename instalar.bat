@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python instalar.py
) else (
    py -3.11 instalar.py
)
if errorlevel 1 (
    echo.
    echo Comprueba Python 3.11 y Docker Desktop, con Docker iniciado.
    pause
    exit /b 1
)
