@echo off
setlocal
cd /d "%~dp0"

where winget >nul 2>nul
if errorlevel 1 (set "HAVE_WINGET=0") else (set "HAVE_WINGET=1")

call :ensure_python
if errorlevel 1 exit /b 1

call :ensure_ffmpeg

:: Un venv rimasto a meta' (o creato con un Python poi disinstallato) non
:: parte: lo si ricrea da zero invece di fidarsi della sola esistenza.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if errorlevel 1 rmdir /s /q ".venv"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creo l'ambiente virtuale...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo.
        echo Errore nella creazione dell'ambiente virtuale.
        pause
        exit /b 1
    )
)

:: Si controllano le dipendenze a ogni avvio (non solo alla creazione del
:: venv), cosi' un'installazione interrotta viene ripresa al lancio successivo.
".venv\Scripts\python.exe" -c "import curl_cffi, yt_dlp, Cryptodome" >nul 2>nul
if errorlevel 1 (
    echo Installo le dipendenze...
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
:: riavviare il PC o riaprire la shell. Il "call set" serve a espandere le
:: variabili contenute nel valore di registro (es. %SystemRoot%\system32),
:: altrimenti finirebbero nel PATH alla lettera e anche "where" smetterebbe
:: di funzionare.
:refreshpath
set "SC_SYSPATH="
set "SC_USERPATH="
for /f "tokens=2,*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SC_SYSPATH=%%B"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "SC_USERPATH=%%B"
call set "PATH=%SC_SYSPATH%;%SC_USERPATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
goto :eof

:: Imposta PY al percorso completo di un Python 3.10+ funzionante, o lo lascia
:: vuoto. Ogni candidato viene eseguito davvero: "where python" da solo non
:: basta, perche' su Windows trova anche l'alias del Microsoft Store, che non
:: e' Python ma apre lo Store.
:find_python
set "PY="
for /f "delims=" %%P in ('py -3 -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY if exist "%PY%" goto :eof
set "PY="
for /f "delims=" %%P in ('python -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY if exist "%PY%" goto :eof
set "PY="
:: L'installer di Python (anche via winget) di default non lo aggiunge al
:: PATH: lo si cerca nelle cartelle d'installazione standard.
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" "%%D\python.exe" -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul && set "PY=%%D\python.exe"
)
goto :eof

:ensure_python
call :find_python
if defined PY goto :eof
if "%HAVE_WINGET%"=="0" (
    echo ERRORE: Python 3.10+ non trovato e winget non e' disponibile su questo PC.
    echo Installa Python da https://www.python.org/downloads/
    echo ^(spunta "Add python.exe to PATH"^), poi rilancia questo script.
    pause
    exit /b 1
)
echo Python non trovato: lo installo con winget ^(puo' volerci qualche minuto^)...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :refreshpath
call :find_python
if defined PY goto :eof
echo.
echo L'installazione di Python sembra fallita. Installalo manualmente da
echo https://www.python.org/downloads/ ^(spunta "Add python.exe to PATH"^)
echo e rilancia questo script.
pause
exit /b 1

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
