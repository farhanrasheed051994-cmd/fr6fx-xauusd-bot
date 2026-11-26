# setup_task.ps1
# Creates ONE scheduled task "FR6FX MT5 Push" with TWO daily triggers (Mon-Fri, laptop LOCAL time):
#   12:20 PM  -> pre-London   (07:20 UTC when laptop is on Pakistan Standard Time)
#    5:20 PM  -> pre-New York (12:20 UTC when laptop is on Pakistan Standard Time)
#
# Usage (normal PowerShell, no admin needed):
#   powershell -ExecutionPolicy Bypass -File .\setup_task.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup_task.ps1 -RunNow      # also fires one test run immediately
#   powershell -ExecutionPolicy Bypass -File .\setup_task.ps1 -PythonExe "C:\Python311\python.exe"

param(
    [string]$RepoDir   = "C:\Projects\FR6_XAUUSD_Automation",
    [string]$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source,
    [string]$TaskName  = "FR6FX MT5 Push",
    [switch]$RunNow
)

# ---------- 1. Safety checks ----------
$tz = Get-TimeZone
if ($tz.Id -ne "Pakistan Standard Time") {
    Write-Warning "Laptop time zone is '$($tz.Id)', NOT 'Pakistan Standard Time'. Task times use LOCAL time, so 12:20 PM would be wrong. Fix the time zone first."
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "python.exe not found. Re-run with -PythonExe 'C:\path\to\python.exe'  (find it with:  py -0p)"
}
if ($PythonExe -like "*WindowsApps*") {
    Write-Warning "This python.exe looks like the Microsoft Store alias, which often fails under Task Scheduler. Prefer a real install path (run: py -0p)."
}

& $PythonExe -c "import MetaTrader5" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The MetaTrader5 package is not installed for $PythonExe  (fix: & '$PythonExe' -m pip install MetaTrader5)"
}

if (-not (Test-Path (Join-Path $RepoDir "mt5_push.py"))) {
    throw "mt5_push.py not found in $RepoDir"
}

# ---------- 2. Wrapper .bat that writes a log you can read ----------
$logDir = Join-Path $RepoDir "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$bat = Join-Path $RepoDir "run_mt5_push.bat"

@"
@echo off
cd /d "$RepoDir"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> "logs\mt5_push.log"
"$PythonExe" mt5_push.py >> "logs\mt5_push.log" 2>&1
echo exit code %errorlevel% >> "logs\mt5_push.log"
exit /b %errorlevel%
"@ | Set-Content -Path $bat -Encoding ASCII

Write-Host "Wrapper written : $bat"

# ---------- 3. The scheduled task ----------
$action = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $RepoDir

$days     = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
$time1    = [datetime]::Today.AddHours(12).AddMinutes(20)   # 12:20 PM
$time2    = [datetime]::Today.AddHours(17).AddMinutes(20)   #  5:20 PM
$trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $time1
$trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $time2

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# Interactive = runs only while you are logged in. MT5 is a desktop app and git uses your saved credentials.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger @($trigger1, $trigger2) `
    -Settings $settings -Principal $principal `
    -Description "FR6FX: export MT5 data and push to GitHub (12:20 PM pre-London, 5:20 PM pre-New York, Mon-Fri)" `
    -Force -ErrorAction Stop | Out-Null

Write-Host ""
Write-Host "Task '$TaskName' registered." -ForegroundColor Green
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult

if ($RunNow) {
    Write-Host "Starting a test run now..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Wait ~30 seconds, then run check_task.ps1 to see the result."
}
