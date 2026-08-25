# -*- coding: utf-8 -*-
"""TE 启动器维护行为监听器（Python 版）：psutil 1 秒轮询进程，捕获 git/pip 命令行。"""
import datetime
import time

import psutil

LOG = r"C:\Users\10987\AppData\Local\Temp\te_monitor.log"

KEYS = ("git", "python", "pip", "cmd", "curl", "wget", "powershell", "7z",
        "comfyui", "bash", "sh")


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")


def main():
    log("=== python monitor started ===")
    known = set()
    for p in psutil.process_iter(["pid"]):
        known.add(p.info["pid"])

    deadline = time.time() + 1800  # 30 分钟
    while time.time() < deadline:
        time.sleep(1)
        try:
            now = set()
            for p in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
                pid = p.info["pid"]
                now.add(pid)
                if pid in known:
                    continue
                name = (p.info["name"] or "").lower()
                if not any(k in name for k in KEYS):
                    continue
                cl = " ".join(p.info["cmdline"] or [])
                cl = cl.replace("\r", " ").replace("\n", " ").strip()
                pp = ""
                try:
                    par = psutil.Process(p.info["ppid"])
                    pcl = " ".join(par.cmdline() or [])
                    pcl = pcl.replace("\r", " ").replace("\n", " ")
                    pp = f"{par.name()}:{pcl[:120]}"
                except Exception:
                    pass
                log(f"P+ PID={pid} PPID={p.info['ppid']} [{pp}] "
                    f"{p.info['name']} :: {cl}")
            known = now
        except Exception:
            pass
    log("=== python monitor ended ===")


if __name__ == "__main__":
    main()
