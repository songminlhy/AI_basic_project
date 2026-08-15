# -*- coding: utf-8 -*-
# run_cleanup_direct.ps1 - 直接运行日志清理（不经过 Windows 定时任务）
# 双击或右键 "使用 PowerShell 运行" 即可
# 参数:
#   .\run_cleanup_direct.ps1              # 执行清理 (默认30天)
#   .\run_cleanup_direct.ps1 -DryRun      # 预览模式 (只看不删)
#   .\run_cleanup_direct.ps1 -Days 14     # 自定义天数

param(
    [switch]$DryRun,
    [int]$Days = 30
)

$PythonExe  = "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe"
$ScriptPath = "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py"
$WorkDir    = "C:\首创证券QMT极速版\mpython"
$HistFile   = "C:\首创证券QMT极速版\mpython\logs\chen_live\cleanup_history.log"

Write-Host ("=" * 60)
Write-Host "日志清理 - 直接运行模式"
Write-Host ("Python    : {0}" -f $PythonExe)
Write-Host ("清理脚本  : {0}" -f $ScriptPath)
$mode = if ($DryRun) { "预览 (DRY-RUN)" } else { "执行清理" }
Write-Host ("模式      : {0}" -f $mode)
Write-Host ("保留天数  : {0}" -f $Days)
Write-Host ("=" * 60)
Write-Host ""

# 路径检查
if (-not (Test-Path $PythonExe))  { Write-Host "[错误] Python 不存在: $PythonExe";  Start-Sleep -Seconds 2; exit 1 }
if (-not (Test-Path $ScriptPath)) { Write-Host "[错误] 清理脚本不存在: $ScriptPath"; Start-Sleep -Seconds 2; exit 1 }
if (-not (Test-Path $WorkDir))    { Write-Host "[错误] 工作目录不存在: $WorkDir";   Start-Sleep -Seconds 2; exit 1 }

# 记录触发前
$beforeLines = 0
if (Test-Path $HistFile) { $beforeLines = (Get-Content $HistFile).Count }

# 组装参数并执行
$argList = @($ScriptPath)
if ($DryRun) { $argList += "--dry-run" }
if ($Days -ne 30) { $argList += "--days"; $argList += $Days }

Set-Location $WorkDir
$cmdLine = "& '{0}' {1}" -f $PythonExe, ($argList -join ' ')
Write-Host (">>> {0}" -f $cmdLine)
Write-Host ""
& $PythonExe @argList
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host ("=" * 60)
if ($exitCode -eq 0) {
    Write-Host "[OK] 清理脚本执行完成 (exit=0)"
    Write-Host ""
    if (Test-Path $HistFile) {
        $afterLines = (Get-Content $HistFile).Count
        $delta = $afterLines - $beforeLines
        Write-Host ("清理历史日志: {0} -> {1} 行 (新增 {2} 行)" -f $beforeLines, $afterLines, $delta)
        Write-Host "清理历史日志 (最后 5 行):"
        Get-Content $HistFile -Tail 5 | ForEach-Object { Write-Host ("  {0}" -f $_) }
    }
} else {
    Write-Host ("[失败] 清理脚本退出码: {0}" -f $exitCode)
}
Write-Host ("=" * 60)
Write-Host ""

# 交互退出: 有UI时3秒等待, 否则立即退出
if ([Environment]::UserInteractive) {
    Write-Host "3秒后自动退出..."
    Start-Sleep -Seconds 3
}
