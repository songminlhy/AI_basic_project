# PowerShell 脚本中文乱码 — 30 秒修复小贴士

> **创建日期**: 2026-08-15
> **触发场景**: `run_cleanup_direct.ps1` / `trigger_cleanup_scheduled.ps1` / 其他 `.ps1` 脚本运行时中文变成 "鏃ュ織娓呯悊" / "鍚姩澶辫触"
> **适用范围**: Windows 10/11 + **PowerShell 5.1**（Win 自带版本）。PowerShell 7+ 已不受此坑影响。

---

## 1. 速诊：你是不是遇到了这个问题？

只要满足 **任意一条**，就是编码问题，不用再排查路径/权限：

| 现象 | 示例 |
|------|------|
| Write-Host 的中文提示全是乱码 | `鏃ュ織娓呯悊宸ュ叿 - 鎵ц娓呯悊` |
| 路径里的"首创证券QMT极速版"被打印成方块/乱码 | `C:\首?????极速版\mpython` |
| `Test-Path` 明明文件存在却报不存在 | 乱码路径解析失败 → 判定不存在 → `exit 1` |
| `Start-ScheduledTask` 返回码正常但 cleanup_history.log 没新增 | 中文参数传给 Python 时被截断 |

**快速验证命令**（复制到 PowerShell 里看哪行是乱的）：
```powershell
Write-Host "--- 正常中文应为 ---"
Write-Host "CleanOldLogs 清理工具"
Write-Host "首创证券QMT极速版"
Write-Host "保留 33 个日志文件"
```

---

## 2. 根因（一句话版）

**PowerShell 5.1 默认用 GBK（代码页 936）解析 `.ps1` 文本，但如果文件被保存成 UTF-8 **无 BOM**，PowerShell 会把 UTF-8 字节当作 GBK 解码 — 结果就是你看到的"鏃ュ織"。**

| 保存格式 | PowerShell 5.1 显示 | PowerShell 7+ 显示 | 推荐？ |
|---------|:-------------------:|:------------------:|:------:|
| **UTF-8 BOM** (0xEF 0xBB 0xBF 开头) | ✅ 正常 | ✅ 正常 | 🟢 **首选** |
| UTF-8 无 BOM | ❌ 乱码 (**本故障根因**) | ✅ 正常 | 🔴 禁止 |
| GBK / ANSI | ✅ 正常 | ⚠️ 可能乱码 | 🟡 仅 .bat 用 |

---

## 3. 修复方案（PowerShell 里粘贴 3 行就行）

### 方案 A：批量修复当前目录所有 `.ps1`（最快 ✅）

```powershell
$enc = New-Object System.Text.UTF8Encoding($true)   # $true = 带 BOM
Get-ChildItem -Path . -Filter "*.ps1" -File | ForEach-Object {
    $raw = [System.IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8)
    [System.IO.File]::WriteAllText($_.FullName, $raw, $enc)
    Write-Host ("OK - {0} -> UTF-8 BOM" -f $_.Name)
}
```

**作用范围**：当前目录 `.ps1` 文件（不含子目录，要递归加 `-Recurse`）。运行后直接再跑脚本，中文必正常。

---

### 方案 B：只修复特定文件（更精准）

```powershell
$enc = New-Object System.Text.UTF8Encoding($true)
$file = ".\trigger_cleanup_scheduled.ps1"   # 改成你要修的文件名
$raw  = [System.IO.File]::ReadAllText($file, [Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($file, $raw, $enc)
Write-Host ("已修复 {0}" -f $file)
```

---

### 方案 C：VS Code / Notepad++ / 记事本 手动设置

| 编辑器 | 操作 |
|--------|------|
| **VS Code** | 状态栏右下角点 `UTF-8` → Save with Encoding → 选 `UTF-8 with BOM` |
| **Notepad++** | 编码 → 选择「UTF-8 BOM」→ 保存 |
| **记事本 (Windows 11)** | 另存为 → 编码下拉选「UTF-8」（Win11 记事本新版默认就是 BOM） |
| **记事本 (Windows 10)** | 另存为 → 编码下拉选「UTF-8」，但 Win10 老版默认无 BOM 可能不稳，建议用方案 A |

---

## 4. 确认修复是否生效

### 4.1 看文件头是否有 BOM（PowerShell）
```powershell
$bytes = [System.IO.File]::ReadAllBytes(".\trigger_cleanup_scheduled.ps1")[0..2]
$bomOk = ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
Write-Host ("UTF-8 BOM: {0}" -f $(if ($bomOk) { "✅ OK" } else { "❌ 未修复, 请重新运行方案A" }))
```
输出 `✅ OK` 即代表编码正确。

### 4.2 实跑验证
```powershell
.\trigger_cleanup_scheduled.ps1
# 看第 [0/3] 行是否正常显示: "关键路径检查" 而非乱码
```

---

## 5. 常见误操作（别再踩）

| 操作 | 结果 |
|------|------|
| ❌ 在脚本开头加 `chcp 65001` | 这是给 .bat/cmd 用的，对 `.ps1` **完全无效**（PowerShell 在加载时就已经解析完了，chcp 只影响之后的 stdout） |
| ❌ `$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8` | 只修复"终端打印出来"的部分，脚本内部**文件解析的乱码依然存在** |
| ❌ 把文件保存为 GBK 来回避问题 | 短期能跑；一旦迁到非中文 Windows（代码页 437）立即崩，且与 Git 上多数项目的 UTF-8 生态冲突 |
| ❌ 用 `ConvertTo-UTF8.ps1` 之类的第三方脚本 | 很容易把原本 GBK 的文件错误识别成 UTF-8，结果二次损坏（变成 "???" 永久丢失） |

---

## 6. 与 `.bat` 编码的区别（避免混淆）

| 文件类型 | 推荐编码 | 根因文档 |
|---------|---------|---------|
| `.ps1` (本小贴士) | **UTF-8 BOM** | 本文档 `PS1_ENCODING_FIX_TIP_20260815.md` |
| `.bat` / `.cmd` | **GBK (936)** + 首行 `chcp 936 >nul` | `BAT_ENCODING_FIX_GUIDE_20260814.md` |
| `.md` / `.py` / `.json` / `.csv` | **UTF-8 无 BOM**（Git/工具链通用） | — |

> 记忆口诀：**ps1 要 BOM，bat 要 GBK，代码文件统统 UTF-8 裸奔**。

---

## 7. 故障复现 & 一键自检脚本

如果你想**验证某台机器是否存在此坑**（例如刚装好的新机器 / 刚 clone 的项目），跑这个：

```powershell
# 会临时生成一个 含中文的 UTF-8 无BOM ps1，运行看是否乱码
$testFile = Join-Path $env:TEMP "_ps1_encoding_check_$(Get-Random).ps1"
@'
Write-Host "[正常应为中文] 清理工具 启动 首创证券 路径 OK"
'@ | Set-Content $testFile -Encoding UTF8   # PS 默认的 -Encoding UTF8 = 无BOM (坑!)
Write-Host "--- 使用 UTF-8 无 BOM 文件运行:" -ForegroundColor Yellow
& $testFile
Write-Host ""
Write-Host "--- 如果上面显示乱码，说明你这台机器 PowerShell 5.1 需要用 UTF-8 BOM"
Write-Host ""
Remove-Item $testFile -Force
```

**结果解读**：
- 打印 `[正常应为中文] 清理工具 启动 首创证券 路径 OK` → 环境正常，无需修复
- 打印 `[鏃ュ織] 鏁寸悊宸ュ叿 ...` → 立即用「方案 A」批量转 BOM

---

## 8. CleanOldLogs 系列脚本修复状态

本项目与 CleanOldLogs 相关的 3 个 `.ps1` 脚本**已经全部修复为 UTF-8 BOM**，并提交到 Git：

| 脚本 | 所在位置 | 编码 | Git commit |
|------|---------|------|-----------|
| `trigger_cleanup_scheduled.ps1` | AI_basic_project 根目录 / `mpython\tools\` | UTF-8 BOM ✅ | `6003927` |
| `run_cleanup_direct.ps1` | AI_basic_project 根目录 / `mpython\tools\` | UTF-8 BOM ✅ | `6003927` |
| `run_cleanup.ps1` | AI_basic_project 根目录 / `mpython\tools\` | UTF-8 BOM ✅ | `6003927` |

> 如果后续修改或新增 `.ps1` 文件后又出现乱码，**直接回本文档第 3 节运行方案 A** 即可，无需再看其他内容。
