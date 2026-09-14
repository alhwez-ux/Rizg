@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo Starting TickChart to Rizg sync...
".venv\Scripts\python.exe" "scripts\sync_uniticker_to_rizg.py" --interval 20
pause
