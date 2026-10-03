# setup_scheduler.ps1
# ------------------------------------------------------------------
# adDominum — daily scheduler setup.
#
# Replaces the old at-logon trigger with a daily 07:58 trigger.
#
# Why: an at-logon trigger only fires when you log in, and silently does
# nothing if the task is disabled, the credentials go stale, or a Windows
# update resets it. A daily trigger with -StartWhenAvailable fires at 07:58,
# and if the machine was switched off at that moment it runs as soon as you
# next boot. That is the behaviour you actually want.
#
# main.py now exits after the final post of the day, so nothing idles
# overnight — the task simply fires again the next morning.
#
# Run from an ELEVATED PowerShell prompt:
#     powershell -ExecutionPolicy Bypass -File setup_scheduler.ps1
# ------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$TaskName    = "adDominum Daily Posting"
$ProjectDir  = "C:\Projects\adDominum"
$BatchFile   = Join-Path $ProjectDir "start_addominum.bat"
$StartTime   = "07:58"

# --- Sanity check -------------------------------------------------
if (-not (Test-Path $BatchFile)) {
    Write-Host "ERROR: Could not find $BatchFile" -ForegroundColor Red
    Write-Host "Check the ProjectDir path at the top of this script." -ForegroundColor Red
    exit 1
}

# --- Remove any previous version of the task ----------------------
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task '$TaskName'..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# --- Action -------------------------------------------------------
$action = New-ScheduledTaskAction `
    -Execute $BatchFile `
    -WorkingDirectory $ProjectDir

# --- Trigger: every day at 07:58 ----------------------------------
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime

# --- Settings -----------------------------------------------------
# StartWhenAvailable        : run late if the PC was off at 07:58
# DontStopIfGoingOnBatteries: keep posting on battery
# ExecutionTimeLimit 14h    : hard stop well after the 20:00 window closes,
#                             so a hung run can never survive into the night
# RestartCount / Interval   : recover from a transient crash
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 14) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

# --- Principal: run as the logged-in user, only when logged on ----
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

# --- Register -----------------------------------------------------
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs the adDominum daily posting plan (08:00-20:00) and exits after the final post." | Out-Null

Write-Host ""
Write-Host "Task '$TaskName' registered successfully." -ForegroundColor Green
Write-Host "  Trigger : daily at $StartTime (runs late if the PC was off)"
Write-Host "  Action  : $BatchFile"
Write-Host "  Logs    : $env:LOCALAPPDATA\adDominum\logs\automation.log"
Write-Host ""
Write-Host "To test it right now without waiting for tomorrow:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To check what happened after a run:" -ForegroundColor Cyan
Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host ""
