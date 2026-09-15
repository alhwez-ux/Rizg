@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONUTF8=1
start "" /MIN ".venv\Scripts\pythonw.exe" "scripts\sync_uniticker_to_rizg.py" --interval 15
echo Rizg is now updating from TickerChart in the background.
echo Keep TickerChart Live open. No extra clicks needed.
timeout /t 3 >nul
