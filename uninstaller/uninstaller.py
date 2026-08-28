# -*- coding: utf-8 -*-
"""ComfyUIBM启动器 卸载程序（轻量版，无 GUI 依赖）。

只删除启动器自己安装的文件（exe / _internal / 卸载程序），
目录中的其他内容一律保留；目录非空时也不删除目录本身。
"""
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "ComfyUIBM启动器"
EXE_NAME = "ComfyUIBM_Launcher.exe"
INTERNAL_DIR = "_internal"

MB_YESNO = 0x0004
MB_ICONQUESTION = 0x0020
IDYES = 6


def _confirm(title: str, text: str) -> bool:
    try:
        ret = ctypes.windll.user32.MessageBoxW(0, text, title,
                                               MB_YESNO | MB_ICONQUESTION)
        return ret == IDYES
    except Exception:
        return True


def _kill_running():
    """结束可能正在运行的启动器进程，否则 exe/_internal 被占用删不掉。"""
    try:
        subprocess.run(["taskkill", "/IM", EXE_NAME, "/F"],
                       capture_output=True, timeout=15,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    except Exception:
        pass


def _lnk_paths():
    home = Path.home()
    menu = (Path(os.environ.get("APPDATA", str(home))) /
            "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [
        home / "Desktop" / f"{APP_NAME}.lnk",
        menu / f"{APP_NAME}.lnk",
        menu / f"卸载 {APP_NAME}.lnk",
    ]


def make_bat(install_dir: Path) -> str:
    """生成延迟清理批处理：只删卸载程序自身与空目录（绝不递归删目录）。"""
    return (
        "@echo off\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'del "{install_dir / "Uninstall.exe"}" >nul 2>&1\r\n'
        'del "%~f0" >nul 2>&1\r\n'
        f'rmdir "{install_dir}" 2>nul\r\n'          # 无 /s：目录非空则不删
    )


def main():
    install_dir = Path(sys.executable).resolve().parent

    if not _confirm(
            "卸载确认",
            f"确定要卸载 {APP_NAME} 吗？\n\n"
            f"将删除启动器文件：\n{install_dir}\\{EXE_NAME}\n"
            f"{install_dir}\\{INTERNAL_DIR}\\n"
            f"{install_dir}\\Uninstall.exe\n\n"
            "（安装目录中的其他内容与 models 模型、custom_nodes 插件、"
            "个人配置均会保留）"):
        return

    # 1. 结束运行中的启动器（否则文件被占用，删除会静默失败）
    _kill_running()

    # 2. 删除快捷方式
    for lnk in _lnk_paths():
        try:
            lnk.unlink()
        except OSError:
            pass

    # 3. 精确删除启动器文件；失败要明确报告，不再静默跳过
    _kill_running()
    shutil.rmtree(install_dir / INTERNAL_DIR, ignore_errors=True)
    try:
        (install_dir / EXE_NAME).unlink()
    except OSError:
        pass
    if (install_dir / EXE_NAME).exists():
        ctypes.windll.user32.MessageBoxW(
            0,
            f"部分文件无法删除（可能仍被占用）：\n{install_dir}\\{EXE_NAME}\n\n"
            f"请关闭 {APP_NAME} 后手动删除该目录，或稍后重试卸载。",
            "卸载未完全完成", 0x0010 | 0x0004)
        return

    # 4. 延迟删除自身（运行中无法删）+ 清理空目录
    bat = install_dir / "__uninstall.bat"
    try:
        bat.write_text(make_bat(install_dir),
                       encoding="gbk", errors="replace")
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/b", str(bat)],
            creationflags=0x08000000 if os.name == "nt" else 0)
    except Exception:
        pass


if __name__ == "__main__":
    main()
