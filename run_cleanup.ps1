# -*- coding: utf-8 -*-
# run_cleanup.ps1 — 日志清理一键运行脚本
# 双击或右键 "使用 PowerShell 运行" 即可执行
# 用法:
#   .\run_cleanup.ps1              # 执行清理 (默认30天)
#   .\run_cleanup.ps1 -DryRun      # 预览模式 (只看不删)
#   .\run_cleanup.ps1 -Days 14     # 自定义天数

param(
    [switch]$DryRun,
    [int]$Days = 30
)

# ===== 配置 =====
$PythonExe = "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe"
$ScriptPath = "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py"
$WorkDir = "C:\首创证券QMT极速版\mpython"

# ===== 执行 =====
Write-Host "=" * 60
Write-Host "日志清理脚本"
Write-Host "Python: $PythonExe"
Write-Host "脚本:   $ScriptPath"
Write-Host "模式:   $(if ($DryRun) { '预览 (DRY-RUN)' } else { '执行清理' })"
Write-Host "天数:   $Days"
Write-Host "=" * 60
Write-Host ""

$args = @()
if ($DryRun) { $args += "--dry-run" }
if ($Days -ne 30) { $args += "--days"; $args += $Days }

Set-Location $WorkDir
& $PythonExe $ScriptPath @args

Write-Host ""
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
