@echo off
:: adDominum -- startup script
:: Called by Windows Task Scheduler on login/restart

set PYTHONPATH=C:\Projects\adDominum
cd /d C:\Projects\adDominum

:: Log the startup time
echo Starting adDominum at %date% %time% >> logs\startup.log

:: Start the automation (runs continuously)
python main.py >> logs\automation.log 2>&1
