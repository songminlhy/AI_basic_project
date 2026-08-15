# -*- coding: utf-8 -*-
# trigger_cleanup_scheduled.ps1 - 手动触发 CleanOldLogs 定时任务
# 双击或右键 "使用 PowerShell 运行" 即可
# 作用: 等效于 Start-ScheduledTask -TaskName "CleanOldLogs"
# 额外: 若任务不存在则自动创建; 注册失败/触发失败均有回退;
#       执行后显示 cleanup_history.log 增量报告 + LastTaskResult 处置建议
#
# 错误处理矩阵:
#   | 阶段               | 失败时                                 | 退出码 |
#   |--------------------|----------------------------------------|--------|
#   | 路径检查(Py/Script)| 报错 + 提示修改变量 L9-11 后退出      | 1      |
#   | Register-ScheduledTask 失败 | try/catch 捕获, 跳过注册, 直接回退为 run Python | 不中断 |
#   | Start-ScheduledTask 失败    | try/catch 捕获, 回退为直接运行 Python | 不中断 |
#   | Fallback Python 抛异常      | try/catch + $LASTEXITCODE 报告        | 不中断 |
#   | 轮询等待超时 30s   | 打印 [警告] 明确标注超时, 继续增量比较 | 不中断 |
#   | LastTaskResult != 0| 末尾给出「重新注册」处置建议           | 不中断 |

$ErrorActionPreference = "Continue"

# === 配置区 (新机器部署时只需要修改这里 3 个路径!) ===
$PythonExe  = "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe"
$ScriptPath = "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py"
$WorkDir    = "C:\首创证券QMT极速版\mpython"
$HistFile   = "C:\首创证券QMT极速版\mpython\logs\chen_live\cleanup_history.log"
# ====================================================

Write-Host ("=" * 60)
Write-Host "CleanOldLogs 手动触发工具"
Write-Host ("=" * 60)
Write-Host ""

# ===== [0/3] 关键路径前置检查 (无论任务是否存在都做一遍) =====
Write-Host "[0/3] 关键路径检查..."
$preCheckOK = $true
if (-not (Test-Path $PythonExe))  { Write-Host ("  [错误] Python 不存在: {0}`n         请修改变量 `$PythonExe (L21) 后重试" -f $PythonExe); $preCheckOK = $false }
if (-not (Test-Path $ScriptPath)) { Write-Host ("  [错误] 清理脚本不存在: {0}`n         请修改变量 `$ScriptPath (L22) 后重试" -f $ScriptPath); $preCheckOK = $false }
if (-not (Test-Path $WorkDir))    { Write-Host ("  [错误] 工作目录不存在: {0}`n         请修改变量 `$WorkDir (L23) 后重试" -f $WorkDir); $preCheckOK = $false }
if ($preCheckOK) { Write-Host "  OK - Python/清理脚本/工作目录均存在" } else { Write-Host ""; Start-Sleep -Seconds 3; exit 1 }
Write-Host ""

# ===== [1/3] 检查/创建定时任务 =====
Write-Host "[1/3] 检查定时任务..."
$task = $null
$registeredOK = $false
try {
    $task = Get-ScheduledTask -TaskName "CleanOldLogs" -ErrorAction Stop
    $user = $task.Principal.UserId
    Write-Host ("  OK - 任务存在 (状态: {0}, 用户: {1})" -f $task.State, $user)
    $registeredOK = $true
} catch {
    Write-Host "  任务不存在, 正在自动创建..."
    try {
        $action   = New-ScheduledTaskAction -Execute $PythonExe -Argument $ScriptPath -WorkingDirectory $WorkDir -ErrorAction Stop
        $trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00AM
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
        $curUser  = "{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME
        Register-ScheduledTask -TaskName "CleanOldLogs" -Action $action -Trigger $trigger -Settings $settings -User $curUser -Description "每周日凌晨3点自动清理logs/chen_live/中超过30天的旧日志文件" -Force -ErrorAction Stop | Out-Null
        Write-Host ("  OK - 已创建 CleanOldLogs (用户: {0})" -f $curUser)
        $registeredOK = $true
    } catch {
        Write-Host ("  [失败] 创建任务失败: {0}" -f $_.Exception.Message)
        Write-Host "  [回退] 不通过定时任务, 改为直接运行 cleanup_old_logs.py (稍后在 [3/3] 执行)"
        $registeredOK = $false   # 标记注册失败, 后续直接走 fallback
    }
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

# ===== [3/3] 触发定时任务 / 回退直连 =====
Write-Host "[3/3] 触发执行..."
$fallback = (-not $registeredOK)   # 注册失败直接进入 fallback
$fallbackRC = $null
if (-not $fallback) {
    try {
        Start-ScheduledTask -TaskName "CleanOldLogs" -ErrorAction Stop
        Write-Host "  Start-ScheduledTask 调用成功"
    } catch {
        Write-Host ("  [失败] Start-ScheduledTask: {0}" -f $_.Exception.Message)
        Write-Host "  [回退] 改为直接运行 cleanup_old_logs.py ..."
        $fallback = $true
    }
}
if ($fallback) {
    Write-Host "  回退模式: 直接运行 Python 清理脚本"
    $origLoc = Get-Location
    try {
        Set-Location $WorkDir -ErrorAction Stop
        & $PythonExe $ScriptPath
        $fallbackRC = $LASTEXITCODE
        Write-Host ("  Python 进程返回码: {0}" -f $(if ($null -eq $fallbackRC) { "N/A" } else { $fallbackRC }))
    } catch {
        Write-Host ("  [异常] Python 运行期间报错: {0}" -f $_.Exception.Message)
        $fallbackRC = -1
    } finally {
        Set-Location $origLoc   # 还原工作目录, 避免影响后续
    }
}
Write-Host ""

# 轮询等待 (仅非 fallback 时需要)
if (-not $fallback) {
    Write-Host "等待脚本执行 (最长 30 秒, 每 3 秒轮询一次)..."
    $waited = 0; $done = $false
    while ($waited -lt 30 -and -not $done) {
        Start-Sleep -Seconds 3; $waited += 3
        try {
            $info = Get-ScheduledTaskInfo -TaskName "CleanOldLogs" -ErrorAction Stop
            # LastRunTime 在 1 分钟内视为刚跑完 (避免时钟/时区细微偏差影响)
            if ($info.LastRunTime -gt (Get-Date).AddMinutes(-1)) { $done = $true }
        } catch {
            # Get-ScheduledTaskInfo 偶发瞬断, 忽略继续等下一轮
        }
    }
    if ($done) {
        Write-Host ("  [OK] 检测到任务完成, 已等待 {0}s" -f $waited)
    } else {
        Write-Host ("  [警告] 轮询超时 ({0}s) — 可能任务仍在后台运行, 或 LastRunTime 未在 1 分钟窗口命中" -f $waited)
        Write-Host "          稍后可手动运行:  Get-ScheduledTaskInfo -TaskName CleanOldLogs  查看结果"
    }
}
Write-Host ""

# ===== 结果报告 =====
Write-Host ("=" * 60)
Write-Host "执行结果"
Write-Host ("=" * 60)
$needReRegister = $false
if (-not $fallback) {
    try {
        $info = Get-ScheduledTaskInfo -TaskName "CleanOldLogs" -ErrorAction Stop
        $rcVal = [int]$info.LastTaskResult
        $rcMap = @{ 0 = "成功"; 1 = "常规错误(脚本路径错/Python找不到)"; 2 = "文件找不到(脚本不存在)"; 267011 = "用户未登录(检查 -User 参数)"; 267014 = "错过触发(下次会补跑)" }
        $rcText = if ($rcMap.ContainsKey($rcVal)) { $rcMap[$rcVal] } else { ("未知返回码 {0}" -f $rcVal) }
        Write-Host ("  上次运行时间 : {0}" -f $info.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss"))
        Write-Host ("  返回码       : {0} ({1})" -f $info.LastTaskResult, $rcText)
        Write-Host ("  遗漏任务数   : {0}" -f $info.NumberOfMissedRuns)
        Write-Host ("  下次自动运行 : {0}" -f $info.NextRunTime.ToString("yyyy-MM-dd HH:mm:ss"))
        if ($rcVal -ne 0 -and $rcVal -ne 267014) { $needReRegister = $true }
    } catch {
        Write-Host ("  无法读取任务信息: {0}" -f $_.Exception.Message)
    }
} else {
    Write-Host "  执行方式: 回退为直接运行 (未经过定时任务)"
    if ($null -ne $fallbackRC) {
        if ($fallbackRC -eq 0) {
            Write-Host "  回退执行结果: 成功 (返回码 0)"
        } else {
            Write-Host ("  回退执行结果: 失败 (返回码 {0})" -f $fallbackRC)
            $needReRegister = $true
        }
    }
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
        Write-Host "  [警告] 无增量写入, 请检查 Python 脚本执行是否异常 (见上方返回码)"
        $needReRegister = $true
    }
} else {
    Write-Host "  [警告] cleanup_history.log 仍不存在, 清理脚本可能未正确启动"
    $needReRegister = $true
}
Write-Host ""

# 处置建议
if ($needReRegister) {
    Write-Host ("-" * 60)
    Write-Host "[处置建议] 检测到异常标记, 建议按顺序排查:"
    Write-Host "  1. 检查顶部 L9-L11 路径变量, 与本机实际路径对齐"
    Write-Host "  2. 手动跑一次:  & '${PythonExe}' '${ScriptPath}' --dry-run"
    Write-Host "  3. 若以上 OK 但定时任务返回非 0, 重建任务:"
    Write-Host "       Unregister-ScheduledTask -TaskName CleanOldLogs -Confirm:`$false"
    Write-Host "       然后重新运行本脚本, 会自动注册新任务"
    Write-Host "  4. 详细 FAQ 见:  C:\首创证券QMT极速版\mpython\docs\CleanOldLogs_部署指南_20260815.md"
    Write-Host ("-" * 60)
    Write-Host ""
}

# 退出
if ([Environment]::UserInteractive) {
    Write-Host "3秒后自动退出..."
    Start-Sleep -Seconds 3
}
