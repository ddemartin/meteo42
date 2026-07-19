@echo off
cd /d D:\Projects\meteo42

if not exist ".venv\Scripts\python.exe" (
    echo Creazione ambiente virtuale...
    py -3.13 -m venv .venv
)

echo Aggiornamento pip...
.venv\Scripts\python.exe -m pip install --upgrade pip

echo Installazione dipendenze...
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Ambiente pronto.

echo D:\Projects\meteo42
echo .venv\Scripts\activate.bat

pause