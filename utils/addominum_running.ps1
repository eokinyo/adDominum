# exit 1 if adDominum main.py is already running, else 0 (used by start_addominum.bat)
$r = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'main\.py' }
if ($r) { exit 1 } else { exit 0 }
