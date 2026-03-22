@echo off
echo Dang build file EXE...
pyinstaller --onefile --windowed --add-data "assets;assets" main.py
echo Build hoan tat!
pause
