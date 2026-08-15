# CleanOldLogs 定时日志清理任务 — 快速部署指南

> 版本: v1.2 | 日期: 2026-08-15
> 适用: Windows 10/11 + PowerShell 5.1+
> 作用: 每周日凌晨 3:00 自动清理 `logs/chen_live/` 中超过 30 天的 `.log` 文件
> 推荐部署方式: 一键脚本 `trigger_cleanup_scheduled.ps1`（自动注册 + 立即触发 + 结果报告，约 10 秒完成）

---

## 一、前提条件

| 项目 | 要求 | 检查命令 |
|------|------|---------|
| Python 路径存在 | `C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe` | `Test-Path "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe"` |
| 清理脚本存在 | `C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py` | `Test-Path "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py"` |
| 日志目录存在 | `C:\首创证券QMT极速版\mpython\logs\chen_live` | `Test-Path "C:\首创证券QMT极速版\mpython\logs\chen_live"` |
| 当前用户 | 普通用户即可（无需管理员） | `whoami` |

> 路径不同时，全部替换为你的实际绝对路径。

---

## 二、最简部署（1 行搞定 · 最推荐 ✅）

直接运行 `trigger_cleanup_scheduled.ps1` 即可完成「检查存在 → 自动注册 → 触发一次 → 报告结果」的全流程：

```powershell
# AI 项目根目录（Git 仓库中已同步）
cd c:\Users\宋敏\Documents\trae_projects\AI_basic_project
.\trigger_cleanup_scheduled.ps1

# 或者策略项目工具目录
cd C:\首创证券QMT极速版\mpython\tools
.\trigger_cleanup_scheduled.ps1
```

脚本会自动执行以下步骤：
1. ✅ 检查 Python、cleanup_old_logs.py、日志目录是否存在
2. ✅ 检查 CleanOldLogs 任务是否已存在（已存在则跳过创建）
3. ✅ 不存在则调用 Register-ScheduledTask 创建任务（每周日 03:00，当前用户）
4. ✅ Start-ScheduledTask 立即触发一次（3~5 秒完成）
5. ✅ 报告 LastTaskResult / LastRunTime / NextRunTime 结果
6. ✅ 末尾给出 cleanup_history.log 的行数统计

> 注意：脚本文件保存为 **UTF-8 BOM** 格式，确保 PowerShell 5.1 中文不乱码。

---

## 三、原始 PowerShell 命令部署（完整可控）

如需手动控制每一步（不使用脚本封装），打开 **PowerShell**（普通用户，非管理员），执行：

```powershell
# ====== 创建 CleanOldLogs 定时任务 ======
$action = New-ScheduledTaskAction `
    -Execute "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe" `
    -Argument "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py" `
    -WorkingDirectory "C:\首创证券QMT极速版\mpython"

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00AM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

$user = "$env:USERDOMAIN\$env:USERNAME"

Register-ScheduledTask `
    -TaskName "CleanOldLogs" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $user `
    -Description "每周日凌晨3点自动清理logs/chen_live/中超过30天的旧日志文件" `
    -Force
```

---

## 四、脚本全集说明

项目共提供 **3 个 PowerShell 脚本**，分别对应不同使用场景：

| 脚本 | 主要用途 | 常用参数 |
|------|---------|---------|
| `trigger_cleanup_scheduled.ps1` | **部署首选**：自动注册/确认定时任务 + 立即触发 + 结果报告（无参数） | 无 |
| `run_cleanup_direct.ps1` | **手动运行首选**：直接调用 Python 清理脚本，带中文输出和 DryRun 校验 | `-DryRun` `-Days N` |
| `run_cleanup.ps1` | 简化版双击脚本，基本功能同 run_cleanup_direct（兼容旧调用） | `-DryRun` `-Days N` |

### 4.1 run_cleanup_direct.ps1（手动运行首选）

双击或运行项目根目录的脚本即可手动执行清理：

```powershell
# 预览模式（只看不删）
.\run_cleanup_direct.ps1 -DryRun

# 执行清理（默认30天）
.\run_cleanup_direct.ps1

# 自定义保留天数
.\run_cleanup_direct.ps1 -Days 14 -DryRun
```

文件位置（两个目录同步）：
- AI 项目: `c:\Users\宋敏\Documents\trae_projects\AI_basic_project\run_cleanup_direct.ps1` （Git 已提交 ✅）
- 策略项目: `C:\首创证券QMT极速版\mpython\tools\run_cleanup_direct.ps1`

### 4.2 trigger_cleanup_scheduled.ps1（部署首选）

每次在新机器部署时只需运行这一个脚本：

```powershell
# 无参数，一键完成"注册+触发+验证"
.\trigger_cleanup_scheduled.ps1
```

关键特性：
- 幂等：任务已存在时不会重复创建
- 容错：若 Start-ScheduledTask 失败，会退化为直接运行 Python 脚本并报告
- 类型安全：LastTaskResult（UInt32）转 int 后匹配返回码文字（0=成功）

文件位置：
- AI 项目: `c:\Users\宋敏\Documents\trae_projects\AI_basic_project\trigger_cleanup_scheduled.ps1` （Git 已提交 ✅）
- 策略项目: `C:\首创证券QMT极速版\mpython\tools\trigger_cleanup_scheduled.ps1`

### 4.3 run_cleanup.ps1（简化版 · 兼容）

使用方式同 `run_cleanup_direct.ps1`，功能一致，建议优先使用 `run_cleanup_direct.ps1`。

---

## 五、日常管理命令

| 操作 | PowerShell 命令 |
|------|----------------|
| **查看任务状态** | `Get-ScheduledTask -TaskName "CleanOldLogs"` |
| **查看上次执行结果** | `Get-ScheduledTaskInfo -TaskName "CleanOldLogs"` |
| **手动触发一次** | `Start-ScheduledTask -TaskName "CleanOldLogs"` |
| **查看清理历史日志** | `Get-Content "C:\首创证券QMT极速版\mpython\logs\chen_live\cleanup_history.log" -Tail 30` |
| **预览下次清理内容** | `& "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe" "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py" --dry-run` |
| **删除定时任务** | `Unregister-ScheduledTask -TaskName "CleanOldLogs" -Confirm:$false` |

### LastTaskResult 返回码说明

| 代码 | 含义 |
|------|------|
| 0 | ✅ 成功 |
| 1 | 常规错误（脚本路径错 / Python 找不到） |
| 2 | 文件找不到（脚本不存在） |
| 267011 | 用户未登录，任务未执行（检查 `-User` 参数是否正确） |
| 267014 | 错过触发时间（下次会补跑，因启用了 StartWhenAvailable） |

---

## 六、清理记录查看

每次运行（无论是否删除文件）都会写入 **`cleanup_history.log`**：

```
文件位置: C:\首创证券QMT极速版\mpython\logs\chen_live\cleanup_history.log
```

示例内容：
```
[2026-08-15 17:48:42] ====================================================================
[2026-08-15 17:48:42] 日志清理工具 - 执行清理
[2026-08-15 17:48:42] 日志目录: C:\首创证券QMT极速版\mpython\logs\chen_live
[2026-08-15 17:48:42] 保留天数: 30 天 (删除 30 天前的日志)
...
[2026-08-15 17:48:44] 统计: 保留 33 个 (23649.5KB), 待删除 0 个 (0.0KB)
[2026-08-15 17:48:44] [INFO] 没有需要清理的旧日志文件
```

快速查看最近一次清理结果：

```powershell
Get-Content "C:\首创证券QMT极速版\mpython\logs\chen_live\cleanup_history.log" -Tail 20
```

---

## 七、自定义参数

### 7.1 修改保留天数（默认 30 天）

**方式 A：临时命令**
```powershell
& "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe" `
    "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py" `
    --days 14 --dry-run
```

**方式 B：修改定时任务参数**
```powershell
$newArgs = "--days 14"   # 改成你要的天数
Set-ScheduledTask -TaskName "CleanOldLogs" -ArgumentList $newArgs
```

### 7.2 修改触发时间（默认每周日 03:00）

```powershell
# 示例：改成每天凌晨 2:30
$newTrigger = New-ScheduledTaskTrigger -Daily -At 2:30AM
Set-ScheduledTask -TaskName "CleanOldLogs" -Trigger $newTrigger
```

### 7.3 修改日志目录

```powershell
& "python.exe" "cleanup_old_logs.py" --dir "D:\你的\日志\目录" --dry-run
```

---

## 八、常见问题排查

### Q1: Start-ScheduledTask 报 "系统找不到指定的文件"
**原因**: 任务丢失（跨会话/重启后）或创建时用了 SYSTEM 用户无权限
**修复**: 重新执行「第三节」的原始创建命令，确保带 `-User $user`；或者更简单，直接重跑 `.\trigger_cleanup_scheduled.ps1` 即可自动修复

### Q2: 任务显示成功，但 cleanup_history.log 没更新
**原因 1**: 定时任务的 Python/脚本路径不对 — 检查路径是否存在
**原因 2**: 脚本异常退出（如目录不存在）— 手动 dry-run 排查：
```powershell
& "C:\首创证券QMT极速版\mpython\strategy_env\Scripts\python.exe" `
    "C:\首创证券QMT极速版\mpython\tools\cleanup_old_logs.py" --dry-run
```

### Q3: 定时任务运行返回 267011（用户未登录）
**原因**: `-User` 指定的用户未登录或已切换
**修复**: 重新创建任务，使用当前 `whoami` 的用户：
```powershell
$user = whoami   # 看看当前是谁
# 然后用第三节的原始命令重新 Register，或直接跑 trigger_cleanup_scheduled.ps1
```

### Q4: cleanup_history.log 本身太大？
**该文件不会被清理脚本删除**（脚本在 ACTIVE_LOG_FILES 之外，但以 `cleanup_` 开头且当天会频繁写入）。如需控制大小，可在 `cleanup_old_logs.py` 顶部自行设置轮转：
```python
CLEANUP_LOG_MAX_KB = 1024   # 超过1MB自动截断头部
if os.path.exists(CLEANUP_LOG_FILE) and os.path.getsize(CLEANUP_LOG_FILE) > CLEANUP_LOG_MAX_KB * 1024:
    # 只保留最新1000行
    lines = open(CLEANUP_LOG_FILE, encoding="utf-8").readlines()[-1000:]
    with open(CLEANUP_LOG_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
```

### Q5: 中文显示为乱码（如 "鏃ュ織娓呯悊"）
**原因**: `.ps1` 脚本保存为 UTF-8 无 BOM，PowerShell 5.1 用 GBK 解析
**修复**: 将脚本重存为 **UTF-8 BOM** 格式，或直接从 Git 仓库拉取已修复的版本（已提交的三个 `.ps1` 都是 UTF-8 BOM）

---

## 九、保护的文件（永不删除，无论天数）

这些文件即使超过 30 天，**如果当天有写入就不会删除**：

```
chen_live_trading.log    # 主交易日志
monitor_detail.log       # 风险监控详细日志
watchdog.log             # 看门狗日志
watchdog_launch.log      # 看门狗启动日志
cleanup_history.log      # 清理自身历史记录（自动保护）
```

---

## 十、文件清单

| 文件 | 路径（AI 项目 / 策略项目） | 作用 |
|------|--------------------------|------|
| 清理脚本 | `tools/cleanup_old_logs.py` | 核心清理逻辑（Python，含 `_audit()` 双记录审计日志） |
| 手动运行 | `run_cleanup_direct.ps1` / `tools/run_cleanup_direct.ps1` | **手动运行首选**：直接调用 Python，支持 `-DryRun`、`-Days`，UTF-8 BOM |
| 一键部署 | `trigger_cleanup_scheduled.ps1` / `tools/trigger_cleanup_scheduled.ps1` | **部署首选**：自动注册+触发+报告，幂等，容错回退，LastTaskResult 类型安全 |
| 简化兼容 | `run_cleanup.ps1` / `tools/run_cleanup.ps1` | 简化版双击脚本，兼容旧调用（功能同 run_cleanup_direct） |
| 部署文档 | `docs/CleanOldLogs_部署指南_20260815.md`（两边目录同步） | 本文档（v1.2） |
| 清理记录 | `logs/chen_live/cleanup_history.log` | 每次运行的审计日志（控制台 + 文件双重记录） |

> Git 提交信息（AI_basic_project 仓库）: `6003927 feat(ops): 添加日志清理脚本 - run_cleanup_direct / trigger_cleanup_scheduled`
