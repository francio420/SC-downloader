@echo off
setlocal
cd /d "%~dp0"

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ATTENZIONE: ffmpeg non e' stato trovato nel PATH di sistema.
    echo Scaricalo da https://www.gyan.dev/ffmpeg/builds/ ^(build "essentials"^),
    echo estrailo e aggiungi la sua cartella "bin" alle variabili d'ambiente PATH.
    echo Il programma si avviera' comunque, ma i download falliranno senza ffmpeg.
    echo.
    pause
)

if not exist ".venv\Scripts\python.exe" (
    echo Prima esecuzione: creo l'ambiente virtuale e installo le dipendenze...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Errore: Python non trovato, o creazione dell'ambiente virtuale fallita.
        echo Installa Python 3.10+ da https://www.python.org/downloads/
        echo ^(durante l'installazione, spunta "Add python.exe to PATH"^).
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Errore durante l'installazione delle dipendenze, vedi sopra.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo Il programma si e' chiuso con un errore, vedi sopra.
    pause
)
