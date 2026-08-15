# -*- coding: utf-8 -*-
# trigger_cleanup_scheduled.ps1 - 手动触发 CleanOldLogs 定时任务
# 双击或右键 "使用 PowerShell 运行" 即可
# 作用: 等效于 Start-ScheduledTask -TaskName "CleanOldLogs"
# 额外: 若任务不存在则自动创建; 执行后显示 cleanup_history.log 增量报告

$ErrorActionPreference = "Continue"

$PythonExe  = "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe"
$ScriptPath = "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py"
$WorkDir    = "C:\首创证券QMT极速版\mpython"
$HistFile   = "C:\首创证券QMT极速版\mpython\logs\chen_live\cleanup_history.log"

Write-Host ("=" * 60)
Write-Host "CleanOldLogs 手动触发工具"
Write-Host ("=" * 60)
Write-Host ""

# ===== [1/3] 检查/创建定时任务 =====
Write-Host "[1/3] 检查定时任务..."
$task = $null
try {
    $task = Get-ScheduledTask -TaskName "CleanOldLogs" -ErrorAction Stop
    $user = $task.Principal.UserId
    Write-Host ("  OK - 任务存在 (状态: {0}, 用户: {1})" -f $task.State, $user)
} catch {
    Write-Host "  任务不存在, 正在自动创建..."
    if (-not (Test-Path $PythonExe))  { Write-Host ("  [错误] Python 不存在: {0}" -f $PythonExe);  Start-Sleep -Seconds 2; exit 1 }
    if (-not (Test-Path $ScriptPath)) { Write-Host ("  [错误] 清理脚本不存在: {0}" -f $ScriptPath); Start-Sleep -Seconds 2; exit 1 }

    $action   = New-ScheduledTaskAction -Execute $PythonExe -Argument $ScriptPath -WorkingDirectory $WorkDir
    $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00AM
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
    $curUser  = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME
    Register-ScheduledTask -TaskName "CleanOldLogs" -Action $action -Trigger $trigger -Settings $settings -User $curUser -Description "每周日凌晨3点自动清理logs/chen_live/中超过30天的旧日志文件" -Force | Out-Null
    Write-Host ("  OK - 已创建 CleanOldLogs (用户: {0})" -f $curUser)
}
Write-Host ""

# ===== [2/3] 记录触发前清理日志状态 =====
Write-Host "[2/3] 记录触发前清理日志状态..."
$beforeLines = 0; $beforeSize = 0
if (Test-Path $HistFile) {
    $beforeLines = (Get-Content $HistFile).Count
    $beforeSize  = [math]::Round((Get-Item $HistFile).Length / 1024, 1)
    Write-Host ("  cleanup_history.log: {0} 行 / {1} KB" -f $beforeLines, $beforeSize)
} else {
    Write-Host "  cleanup_history.log 不存在 (首次运行会自动创建)"
}
Write-Host ""

# ===== [3/3] 触发定时任务并等待执行完成 =====
Write-Host "[3/3] 触发定时任务并等待执行完成..."
$fallback = $false
try {
    Start-ScheduledTask -TaskName "CleanOldLogs" -ErrorAction Stop
    Write-Host "  Start-ScheduledTask 调用成功"
} catch {
    Write-Host ("  [失败] Start-ScheduledTask: {0}" -f $_.Exception.Message)
    Write-Host ""
    Write-Host "  退化为直接运行 cleanup_old_logs.py ..."
    $fallback = $true
    Set-Location $WorkDir
    & $PythonExe $ScriptPath
}
Write-Host ""

# 轮询等待
if (-not $fallback) {
    Write-Host "等待脚本执行 (最长 30 秒)..."
    $waited = 0; $done = $false
    while ($waited -lt 30 -and -not $done) {
        Start-Sleep -Seconds 3; $waited += 3
        try {
            $info = Get-ScheduledTaskInfo -TaskName "CleanOldLogs" -ErrorAction Stop
            if ($info.LastRunTime -gt (Get-Date).AddMinutes(-1)) { $done = $true }
        } catch {}
    }
    Write-Host ("  已等待 {0}s" -f $waited)
}
Write-Host ""

# ===== 结果报告 =====
Write-Host ("=" * 60)
Write-Host "执行结果"
Write-Host ("=" * 60)
if (-not $fallback) {
    try {
        $info = Get-ScheduledTaskInfo -TaskName "CleanOldLogs" -ErrorAction Stop
        $rcVal = [int]$info.LastTaskResult
        $rcMap = @{ 0 = "成功"; 1 = "常规错误"; 2 = "文件找不到"; 267011 = "用户未登录"; 267014 = "错过触发(下次补跑)" }
        $rcText = if ($rcMap.ContainsKey($rcVal)) { $rcMap[$rcVal] } else { ("未知返回码 {0}" -f $rcVal) }
        Write-Host ("  上次运行时间 : {0}" -f $info.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss"))
        Write-Host ("  返回码       : {0} ({1})" -f $info.LastTaskResult, $rcText)
        Write-Host ("  遗漏任务数   : {0}" -f $info.NumberOfMissedRuns)
        Write-Host ("  下次自动运行 : {0}" -f $info.NextRunTime.ToString("yyyy-MM-dd HH:mm:ss"))
    } catch {
        Write-Host ("  无法读取任务信息: {0}" -f $_.Exception.Message)
    }
} else {
    Write-Host "  执行方式: 回退为直接运行 (未经过定时任务)"
}
Write-Host ""

# cleanup_history.log 增量
if (Test-Path $HistFile) {
    $afterLines = (Get-Content $HistFile).Count
    $afterSize  = [math]::Round((Get-Item $HistFile).Length / 1024, 1)
    $delta      = $afterLines - $beforeLines
    Write-Host ("清理日志增量: {0} -> {1} 行 (新增 {2} 行)" -f $beforeLines, $afterLines, $delta)
    Write-Host ("              {0} -> {1} KB" -f $beforeSize, $afterSize)
    if ($delta -gt 0) {
        Write-Host ""
        Write-Host "---- 最后 10 行摘要 ----"
        Get-Content $HistFile -Tail 10 | ForEach-Object { Write-Host ("  {0}" -f $_) }
    } else {
        Write-Host "  [警告] 无增量写入, 请检查脚本执行是否异常"
    }
}
Write-Host ""

# 退出
if ([Environment]::UserInteractive) {
    Write-Host "3秒后自动退出..."
    Start-Sleep -Seconds 3
}
