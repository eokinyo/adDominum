# exit 0 = papal catch-up due; exit 1 = not due. Prints the reason.
param([string]$Proj = 'C:\Projects\adDominum')
$now = if ($env:ADDOM_TEST_NOW) { [datetime]$env:ADDOM_TEST_NOW } else { Get-Date }
$sched = @{ 'Wednesday' = '11:00'; 'Sunday' = '12:30' }
$d = "$($now.DayOfWeek)"
if (-not $sched.ContainsKey($d)) { "not a papal day - $d"; exit 1 }
if ($now.TimeOfDay -lt [timespan]$sched[$d]) { "before $($sched[$d]) on $d"; exit 1 }
$ymd = $now.ToString('yyyyMMdd')
if (Test-Path "$Proj\logs\papal-done-$ymd.flag") { "papal-done-$ymd.flag exists"; exit 1 }
$log = "$Proj\logs\papal_log.csv"
if (Test-Path $log) {
  foreach ($l in Get-Content $log) {
    $ts = ($l -split ',')[0]; $t = [datetime]::MinValue
    if ([datetime]::TryParse($ts, [ref]$t) -and $t.ToLocalTime().Date -eq $now.Date) { "papal_log already has a post today"; exit 1 }
  }
}
if (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'papal_feed\.py' }) { "papal_feed already running"; exit 1 }
"due - $d after $($sched[$d]), not yet run today"; exit 0
