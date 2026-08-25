# -*- coding: utf-8 -*-
"""验证安装器核心逻辑：资源定位 / 文件复制 / 快捷方式创建。"""
import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "installer"))

import installer  # noqa: E402

TMP = ROOT / ".inst_tmp"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(exist_ok=True)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    # 1. 资源定位
    src = installer.source_dir()
    check("定位到应用资源", (src / installer.EXE_NAME).exists(), str(src))

    # 2. 文件复制
    dst = TMP / "installed"
    uninst_src = installer.uninstall_source()
    check("定位到卸载程序", uninst_src is not None and uninst_src.exists(),
          str(uninst_src))
    worker = installer.InstallWorker(src, dst, uninst_src)
    progress_log = []

    def on_progress(cur, total, name):
        progress_log.append((cur, total, name))

    def on_done(result):
        check("安装完成回调", result == str(dst), result)

    worker.progress.connect(on_progress)
    worker.done.connect(on_done)
    worker.run()  # 直接同步执行（QThread.run 内逻辑）
    n_dst = len([f for f in dst.rglob("*") if f.is_file()])
    n_src = len([f for f in src.rglob("*") if f.is_file()])
    check("文件全部复制（含卸载程序）", n_dst == n_src + 1, f"{n_dst}/{n_src}")
    check("exe 就位", (dst / "ComfyUIBM_Launcher.exe").exists())
    check("卸载程序就位", (dst / "Uninstall.exe").exists())
    check("进度信号触发", len(progress_log) == n_src + 1)

    # 3. 快捷方式创建（PowerShell COM）
    lnk = TMP / "测试快捷方式.lnk"
    exe = dst / "ComfyUIBM_Launcher.exe"
    ok = installer.create_shortcut(lnk, exe, dst)
    check("快捷方式创建", ok and lnk.exists(), str(lnk))

    # 4. 卸载批处理安全性：只删空目录，绝不递归删除
    import uninstaller.uninstaller as un_mod
    bat_text = un_mod.make_bat(dst)
    check("卸载批处理不含递归删除(/s)",
          "/s" not in bat_text and "rmdir /s" not in bat_text,
          bat_text.replace("\r", " ")[:120])
    check("卸载批处理含空目录清理",
          'rmdir "' + str(dst) + '"' in bat_text)

    print("==")
    print(f"INSTALLER TEST: passed={passed} failed={failed}")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
