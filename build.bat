@echo off
echo ╔═══════════════════════════════════╗
echo ║   SPOT CUTTER — Build Tool  ║
echo ╚═══════════════════════════════════╝
echo.

echo [0/2] Attivazione ambiente virtuale...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERRORE: venv non trovato. Assicurati di avere il venv nella cartella del progetto.
    pause
    exit /b 1
)

echo [1/2] Compilazione con PyInstaller...
pyinstaller SpotCutter.spec
if errorlevel 1 (
    echo ERRORE: Compilazione fallita.
    pause
    exit /b 1
)

echo [2/2] Creazione struttura cartelle...
python post_build.py

echo.
echo Build completata!
pause
exit /b 0