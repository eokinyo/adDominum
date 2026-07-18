# setup_scheduler.ps1
# Run as Administrator

$TaskName   = "adDominum"
$ProjectDir = "C:\Users\ellyo\OneDrive\Work\X\Automation\adDominum"
$PythonExe  = (Get-Command python).Source

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task."
}

# Call Python directly - no batch file needed
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "main.py" `
    -WorkingDirectory $ProjectDir

# Set PYTHONPATH as an environment variable for the task
$Env = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

# Trigger at log on
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName    $TaskName `
    -Action      $Action `
    -Trigger     $Trigger `
    -Principal   $Env `
    -Settings    $Settings `
    -Description "adDominum Catholic devotional automation"

# Set PYTHONPATH in the task XML directly
$Task = Get-ScheduledTask -TaskName $TaskName
$Task.Actions[0].WorkingDirectory = $ProjectDir
$Task | Set-ScheduledTask

Write-Host ""
Write-Host "Registered. Starting now..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3
$State = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "State: $State" -ForegroundColor Green
