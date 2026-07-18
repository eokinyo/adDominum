# setup_papal_scheduler.ps1
# Registers two scheduled tasks for the papal feed:
#   - Wednesday at 11:00 AM
#   - Sunday at 12:30 PM
# Run as Administrator

$ProjectDir = "C:\Users\ellyo\OneDrive\Work\X\Automation\adDominum"
$PythonExe  = (Get-Command python).Source

function Register-PapalTask {
    param($TaskName, $DayOfWeek, $Hour, $Minute)

    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed existing: $TaskName"
    }

    $Action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "publishing\papal_feed.py --live" `
        -WorkingDirectory $ProjectDir

    # Weekly trigger on the specified day
    $Trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek $DayOfWeek `
        -At "$($Hour):$($Minute.ToString('D2'))"

    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -RestartCount 2 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    $Principal = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName    $TaskName `
        -Action      $Action `
        -Trigger     $Trigger `
        -Principal   $Principal `
        -Settings    $Settings `
        -Description "adDominum papal feed - $DayOfWeek"

    Write-Host "Registered: $TaskName ($DayOfWeek at $($Hour):$($Minute.ToString('D2')))" -ForegroundColor Green
}

# Register both tasks
Register-PapalTask -TaskName "adDominum_Wednesday" -DayOfWeek Wednesday -Hour 11 -Minute 0
Register-PapalTask -TaskName "adDominum_Sunday"    -DayOfWeek Sunday    -Hour 12 -Minute 30

# Also ensure the main adDominum task has PYTHONPATH set correctly
Write-Host ""
Write-Host "Updating main adDominum task environment..." -ForegroundColor Yellow

# Check main task exists
if (Get-ScheduledTask -TaskName "adDominum" -ErrorAction SilentlyContinue) {
    Write-Host "Main task found." -ForegroundColor Green
} else {
    Write-Host "WARNING: Main adDominum task not found. Run setup_scheduler.ps1 first." -ForegroundColor Red
}

Write-Host ""
Write-Host "Papal feed scheduled:" -ForegroundColor Green
Write-Host "  Wednesday 11:00 AM - General Audience"
Write-Host "  Sunday    12:30 PM - Angelus"
Write-Host ""
Write-Host "To test right now:"
Write-Host "  cd `"$ProjectDir`""
Write-Host "  python publishing\papal_feed.py --live"
