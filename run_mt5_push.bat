@echo off
cd /d "C:\Projects\FR6_XAUUSD_Automation"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> "logs\mt5_push.log"
"C:\Users\farha\AppData\Local\Programs\Python\Python314\python.exe" mt5_push.py >> "logs\mt5_push.log" 2>&1
echo exit code %errorlevel% >> "logs\mt5_push.log"
exit /b %errorlevel%
