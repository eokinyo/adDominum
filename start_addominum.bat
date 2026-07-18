@echo off
:: adDominum -- startup script
:: Called by Windows Task Scheduler on login/restart

set PYTHONPATH=C:\Users\ellyo\OneDrive\Work\X\Automation\adDominum
cd /d C:\Users\ellyo\OneDrive\Work\X\Automation\adDominum

:: Log the startup time
echo Starting adDominum at %date% %time% >> logs\startup.log

:: Start the automation (runs continuously)
python main.py >> logs\automation.log 2>&1
