@echo off
echo Dang build file EXE...
venv\Scripts\pyinstaller.exe --onefile --windowed --add-data "assets;assets" main.py
echo Build hoan tat!
pause
