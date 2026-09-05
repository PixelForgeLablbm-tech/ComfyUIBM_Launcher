# -*- coding: utf-8 -*-
"""系统信息：GPU（nvidia-smi）、内存、端口检测。"""
import ctypes
import json
import os
import re
import socket
import subprocess

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def port_open(port, host="127.0.0.1", timeout=1.0) -> bool:
    """检测本机端口是否已被监听。"""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False


def port_owner_pids(port) -> list:
    """返回监听指定端口（任意地址）的进程 PID 列表（Windows netstat）。

    端口被进程树里多个进程占用时可能返回多个 PID；找不到返回 []。
    """
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, creationflags=NO_WINDOW,
        )
    except Exception:
        return []
    pids = []
    for line in out.stdout.splitlines():
        parts = line.split()
        # TCP   127.0.0.1:8188   0.0.0.0:0   LISTENING   1234
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
            local = parts[1]
            try:
                if local.startswith("["):            # [::1]:8188
                    _lip, lport = local.rsplit("]:", 1)
                else:
                    _lip, lport = local.rsplit(":", 1)
                if int(lport) == port:
                    try:
                        pid = int(parts[4])
                        if pid and pid not in pids:
                            pids.append(pid)
                    except ValueError:
                        pass
            except ValueError:
                continue
    return pids


def process_cmdline(pid) -> str:
    """查询单个进程的命令行（Windows PowerShell）；失败返回空串。"""
    if os.name != "nt" or not pid:
        return ""
    script = ("Get-CimInstance Win32_Process -Filter 'ProcessId=%d' | "
              "Select-Object -ExpandProperty CommandLine" % pid)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15, creationflags=NO_WINDOW,
        )
    except Exception:
        return ""
    if out.returncode != 0:
        return ""
    return (out.stdout or "").strip()


def cmdline_snapshot() -> dict:
    """所有进程 PID→命令行（Windows PowerShell 一次性取全）。

    供低频场景（进程消失后判断是否被外部重启接管）使用；失败返回 {}。
    """
    if os.name != "nt":
        return {}
    script = ("Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15, creationflags=NO_WINDOW,
        )
    except Exception:
        return {}
    if out.returncode != 0:
        return {}
    try:
        data = json.loads(out.stdout or "[]")
    except Exception:
        return {}
    if isinstance(data, dict):
        data = [data]
    res = {}
    for row in data:
        try:
            pid = int(row.get("ProcessId") or 0)
            cmd = row.get("CommandLine")
            if pid and cmd:
                res[pid] = cmd
        except (TypeError, ValueError):
            continue
    return res



def gpu_info() -> list:
    """解析 nvidia-smi 输出：名称 / 显存总 / 已用 / 利用率 / 温度。"""
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, creationflags=NO_WINDOW,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue

            def num(v):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0
            gpus.append({
                "name": parts[0],
                "mem_total": int(num(parts[1])),
                "mem_used": int(num(parts[2])),
                "util": num(parts[3]),
                "temp": num(parts[4]),
            })
        return gpus
    except Exception:
        return []


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_info():
    """返回 (总量, 已用) 字节；失败返回 (0, 0)。"""
    if os.name == "nt":
        try:
            m = _MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(m)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                total = int(m.ullTotalPhys)
                used = int(m.ullTotalPhys - m.ullAvailPhys)
                return total, used
        except Exception:
            pass
    try:
        # Linux/macOS 兜底
        with open("/proc/meminfo", encoding="utf-8") as f:
            data = {}
            for line in f:
                k, _, v = line.partition(":")
                data[k.strip()] = int(v.split()[0]) * 1024
        total = data.get("MemTotal", 0)
        free = data.get("MemFree", 0) + data.get("Buffers", 0) + data.get("Cached", 0)
        return total, max(total - free, 0)
    except Exception:
        return 0, 0


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def clean_log_chunk(raw: str):
    """清理一行原始日志：去 ANSI 转义码，按 \\r 拆分成多条完整日志。"""
    text = _ANSI_RE.sub("", raw)
    return [p.strip() for p in text.split("\r") if p.strip()]
