# -*- coding: utf-8 -*-
"""验证启动选项（Force FP16 等四个复选框）能否记住选择。"""
import os
import sys
import json
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

QMessageBox.information = lambda *a, **k: QMessageBox.Ok
QMessageBox.warning = lambda *a, **k: QMessageBox.Ok
QMessageBox.critical = lambda *a, **k: QMessageBox.Ok

from ui.main_window import MainWindow  # noqa: E402

CFG = ROOT / ".opt_tmp" / "config.json"
CFG.parent.mkdir(parents=True, exist_ok=True)

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
    app = QApplication([])

    # 1. 启动第一个窗口，修改四个选项
    win1 = MainWindow(config_path=str(CFG))
    win1.show()
    app.processEvents()
    t = win1.launch_tab
    t.cb_fp16.setChecked(True)
    t.cb_listen.setChecked(True)
    t.cb_autobrowser.setChecked(False)
    t.cb_autorestart.setChecked(True)
    app.processEvents()

    # 2. 检查配置文件里的值
    data = json.loads(CFG.read_text(encoding="utf-8"))
    launch = data["settings"]["launch"]
    check("配置已保存 force_fp16", launch.get("force_fp16") is True,
          str(launch))
    check("配置已保存 listen", launch.get("listen") is True)
    check("配置已保存 auto_launch_browser=False",
          launch.get("auto_launch_browser") is False)
    check("配置已保存 auto_restart", launch.get("auto_restart") is True)

    # 3. 关闭后重建主窗口（模拟重启）
    win1.pm.shutdown()
    win1.close()
    app.processEvents()
    win2 = MainWindow(config_path=str(CFG))
    win2.show()
    app.processEvents()
    t2 = win2.launch_tab
    check("重启后 force_fp16 保持勾选", t2.cb_fp16.isChecked() is True)
    check("重启后 listen 保持勾选", t2.cb_listen.isChecked() is True)
    check("重启后 auto_launch_browser 保持取消",
          t2.cb_autobrowser.isChecked() is False)
    check("重启后 auto_restart 保持勾选", t2.cb_autorestart.isChecked() is True)
    win2.pm.shutdown()

    print("==")
    print(f"OPTION TEST: passed={passed} failed={failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
