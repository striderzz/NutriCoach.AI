@echo off
rem Builds NutriCoachAI.exe (single file, no console) with the icon and UI bundled.
cd /d "%~dp0"
venv\Scripts\python.exe -m pip install -q pyinstaller
venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name NutriCoachAI ^
  --icon static\icon.ico --add-data "templates;templates" --add-data "static;static" desktop.py
copy /y dist\NutriCoachAI.exe . >nul && echo Built NutriCoachAI.exe
