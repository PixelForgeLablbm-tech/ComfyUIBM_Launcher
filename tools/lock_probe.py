# -*- coding: utf-8 -*-
"""安全探测：v1.2.1 应用退出耗时 & 退出后 exe 锁何时释放（不写 exe）。"""
import ctypes
import os
import time

EXE = r"F:\BM\ComfyUIBM_Launcher.exe"
u32 = ctypes.windll.user32

# 找该 exe 的主窗口并优雅关闭（等价于更新时的退出）
import psutil

target = None
for p in psutil.process_iter(["name", "exe", "pid"]):
    if p.info["name"] == "ComfyUIBM_Launcher.exe" and p.info["exe"] and \
            p.info["exe"].lower() == EXE.lower():
        target = p
        break
if not target:
    print("没有运行中的 F:\\BM 实例")
    raise SystemExit

pid = target.pid
print("实例 PID:", pid)


def _enum_windows():
    res = []
    P = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(h, l):
        res.append(h)
        return True
    u32.EnumWindows(P(cb), 0)
    return res


def is_locked():
    """尝试以追加模式打开（不写入任何字节）——运行中的 exe 会拒绝。"""
    try:
        with open(EXE, "ab"):
            return False
    except PermissionError:
        return True


print("运行中 exe 是否被锁:", is_locked())

# 发 WM_CLOSE 优雅关闭
WM_CLOSE = 0x0010
for hwnd in _enum_windows():
    p = ctypes.c_ulong()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    if p.value == pid:
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

t0 = time.time()
gone = False
for _ in range(80):
    if not psutil.pid_exists(pid):
        gone = True
        break
    time.sleep(0.25)
if gone:
    print("进程退出耗时: %.1f 秒" % (time.time() - t0))
    # 退出后多久可写
    t1 = time.time()
    while time.time() - t1 < 15:
        if not is_locked():
            print("退出后 %.1f 秒 exe 解锁（可替换）" % (time.time() - t1))
            break
        time.sleep(0.5)
    else:
        print("退出后 15 秒仍被锁！")
else:
    print("80 秒内未退出！")
