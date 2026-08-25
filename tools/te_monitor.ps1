# TE 启动器维护行为监听器 v2（无管理员权限版：轮询 + 文件监听）
$log = "C:\Users\10987\AppData\Local\Temp\te_monitor.log"
"=== monitor v2 started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Encoding utf8

# ---------- 文件变动（.NET FileSystemWatcher，无需管理员） ----------
function Add-Watcher($path, [bool]$recursive) {
    if (-not (Test-Path $path)) { "SKIP $path" | Out-File -Append -Encoding utf8 $log; return }
    $fsw = New-Object System.IO.FileSystemWatcher
    $fsw.Path = $path
    $fsw.IncludeSubdirectories = $recursive
    $fsw.NotifyFilter = 'FileName, LastWrite, DirectoryName'
    $fsw.EnableRaisingEvents = $true
    $action = {
        $e2 = $event.SourceEventArgs
        "F  $(Get-Date -Format 'HH:mm:ss.fff') $($e2.FullPath) [$($e2.ChangeType)]" | Out-File -Append -Encoding utf8 $log
    }
    $null = Register-ObjectEvent $fsw -EventName Created -Action $action
    $null = Register-ObjectEvent $fsw -EventName Changed -Action $action
    $null = Register-ObjectEvent $fsw -EventName Deleted -Action $action
    "WATCH $path (recursive=$recursive)" | Out-File -Append -Encoding utf8 $log
}

Add-Watcher "F:\ComfyUI\ComfyUI TE模式启动器 v7.2.0" $true
Add-Watcher "F:\ComfyUI\ComfyUI-aki-v3\ComfyUI\.git" $true
Add-Watcher "F:\ComfyUI\ComfyUI-aki-v3\ComfyUI" $false
Add-Watcher "F:\ComfyUI\ComfyUI_windows_portable_nvidia" $true
Add-Watcher "E:\ComfyUI\ComfyUI-aki-v3\ComfyUI\.git" $true
Add-Watcher "E:\ComfyUI\ComfyUI-aki-v3\ComfyUI" $false

# ---------- 1 秒轮询：新进程 + 完整命令行 ----------
$known = @{}
$snap = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
foreach ($p in $snap) { $known[$p.ProcessId] = $true }

for ($i = 0; $i -lt 1800; $i++) {            # 30 分钟
    Start-Sleep -Seconds 1
    if ($i % 300 -eq 0) {
        "HB $(Get-Date -Format 'HH:mm:ss')" | Out-File -Append -Encoding utf8 $log
    }
    try {
        $now = @{}
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $now[$p.ProcessId] = $true
            if (-not $known.ContainsKey($p.ProcessId)) {
                if ($p.Name -match 'git|python|pip|cmd|curl|wget|powershell|7z|ComfyUI') {
                    $cl = (($p.CommandLine) -replace "`r?`n", " ").Trim()
                    $pp = ""
                    if ($p.ParentProcessId) {
                        $ppc = $procs | Where-Object { $_.ProcessId -eq $p.ParentProcessId }
                        if ($ppc) {
                            $pc = (($ppc.CommandLine) -replace "`r?`n", " ").Trim()
                            $pp = "$($ppc.Name):$($pc.Substring(0, [Math]::Min(100, $pc.Length)))"
                        }
                    }
                    "P+ $(Get-Date -Format 'HH:mm:ss.fff') PID=$($p.ProcessId) PPID=$($p.ParentProcessId) [$pp] $($p.Name) :: $cl" | Out-File -Append -Encoding utf8 $log
                }
            }
        }
        $known = $now
    } catch { }
}

"=== monitor ended $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -Append -Encoding utf8 $log
