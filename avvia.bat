@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

where winget >nul 2>nul
if errorlevel 1 (set "HAVE_WINGET=0") else (set "HAVE_WINGET=1")

call :ensure_python
if errorlevel 1 exit /b 1

call :ensure_ffmpeg

if not exist ".venv\Scripts\python.exe" (
    echo Prima esecuzione: creo l'ambiente virtuale e installo le dipendenze...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo Errore nella creazione dell'ambiente virtuale.
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
exit /b 0

:: Rilegge PATH da registro (HKLM+HKCU) cosi' un'installazione fatta con
:: winget in questa stessa esecuzione diventa visibile subito, senza dover
:: riavviare il PC o riaprire la shell.
:refreshpath
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SC_SYSPATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "SC_USERPATH=%%B"
set "PATH=%SC_SYSPATH%;%SC_USERPATH%"
goto :eof

:ensure_python
where python >nul 2>nul
if not errorlevel 1 goto :eof
if "%HAVE_WINGET%"=="0" (
    echo ERRORE: Python non trovato e winget non e' disponibile su questo PC.
    echo Installa Python 3.10+ da https://www.python.org/downloads/
    echo ^(spunta "Add python.exe to PATH"^), poi rilancia questo script.
    pause
    exit /b 1
)
echo Python non trovato: lo installo con winget ^(puo' volerci qualche minuto^)...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
call :refreshpath
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo L'installazione di Python sembra fallita, oppure serve riavviare il PC
    echo perche' il PATH venga aggiornato. Riavvia e rilancia questo script,
    echo oppure installalo manualmente da https://www.python.org/downloads/
    pause
    exit /b 1
)
goto :eof

:ensure_ffmpeg
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :eof
if "%HAVE_WINGET%"=="0" (
    echo ATTENZIONE: ffmpeg non trovato e winget non e' disponibile su questo PC.
    echo Scaricalo da https://www.gyan.dev/ffmpeg/builds/ ^(build "essentials"^),
    echo estrailo e aggiungi la sua cartella "bin" al PATH manualmente.
    echo Il programma si avviera' comunque, ma i download falliranno senza ffmpeg.
    pause
    goto :eof
)
echo ffmpeg non trovato: lo installo con winget ^(puo' volerci qualche minuto^)...
winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
call :refreshpath
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo.
    echo L'installazione di ffmpeg sembra fallita, oppure serve riavviare il PC
    echo perche' il PATH venga aggiornato. Se i download falliscono, riavvia
    echo il PC e rilancia questo script.
    pause
)
goto :eof
