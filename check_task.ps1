# check_task.ps1 - one-shot health check for the FR6FX scheduled task
# Usage:  powershell -ExecutionPolicy Bypass -File .\check_task.ps1

param(
    [string]$TaskName = "FR6FX MT5 Push",
    [string]$RepoDir  = "C:\Projects\FR6_XAUUSD_Automation"
)

$tz = Get-TimeZone
Write-Host "--- CLOCK ---" -ForegroundColor Cyan
Write-Host "Laptop time zone : $($tz.Id)  (UTC offset $($tz.BaseUtcOffset))"
Write-Host "Local time now   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "UTC time now     : $((Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))"
if ($tz.Id -ne "Pakistan Standard Time") {
    Write-Host "WARNING: not on Pakistan Standard Time - 12:20 PM / 5:20 PM will fire at the wrong moment." -ForegroundColor Red
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "`nTask '$TaskName' NOT FOUND. Run setup_task.ps1 first." -ForegroundColor Red
    return
}
$info = $task | Get-ScheduledTaskInfo

Write-Host "`n--- TASK ---" -ForegroundColor Cyan
Write-Host "State            : $($task.State)"
foreach ($t in $task.Triggers) {
    Write-Host ("Trigger          : {0:HH:mm} local time (Mon-Fri)" -f ([datetime]$t.StartBoundary))
}
Write-Host "Next run         : $($info.NextRunTime)"
Write-Host "Last run         : $($info.LastRunTime)"

$meaning = switch ($info.LastTaskResult) {
    0       { "success" }
    267011  { "task has not run yet" }
    267009  { "running right now" }
    1       { "script returned an error - read the log below" }
    2       { "file not found - check Python path / repo path" }
    default { "see the log below" }
}
Write-Host ("Last result      : 0x{0:X}  ({1})" -f $info.LastTaskResult, $meaning)

Write-Host "`n--- LAST 10 LOG LINES ---" -ForegroundColor Cyan
$log = Join-Path $RepoDir "logs\mt5_push.log"
if (Test-Path $log) { Get-Content $log -Tail 10 } else { Write-Host "No log yet ($log)" }

Write-Host "`n--- LAST GIT COMMIT (should match the last run time) ---" -ForegroundColor Cyan
git -C $RepoDir log -1 --format="%h  %cd  %s" --date=iso
