# -*- coding: utf-8 -*-
"""冒烟测试：离屏启动主窗口，遍历各页面，并做一次进程启动/停止端到端。

用法: python tests/smoke_test.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox

# 屏蔽消息框，避免阻塞测试
QMessageBox.information = lambda *a, **k: QMessageBox.Ok
QMessageBox.warning = lambda *a, **k: QMessageBox.Ok
QMessageBox.critical = lambda *a, **k: QMessageBox.Ok
QMessageBox.question = lambda *a, **k: QMessageBox.Yes
QMessageBox.exec_ = lambda self: QMessageBox.Rejected

from ui.main_window import MainWindow  # noqa: E402
from ui import dialogs  # noqa: E402
from launcher.instance import Instance  # noqa: E402
from launcher.process_manager import ProcessManager  # noqa: E402

# 测试用的临时目录（必须 Path.mkdir 创建，沙箱下 tempfile 目录不可写）
TEST_DIR = ROOT / ".smoke_tmp"
TEST_DIR.mkdir(exist_ok=True)


def dialog_probe(win):
    """构造并切换各对话框的显示模式，验证不崩溃。"""
    d = dialogs.InstanceDialog()
    for i in range(d.cb_type.count()):
        d.cb_type.setCurrentIndex(i)
    d2 = dialogs.InstanceDialog()
    d2.cb_type.setCurrentIndex(1)
    d2.cb_type.setCurrentIndex(0)
    d2.close()
    d.close()
    p = dialogs.PluginInstallDialog()
    p.rb_local.setChecked(True)
    p.rb_git.setChecked(True)
    p.close()
    print("DIALOGS OK")


def process_e2e(app):
    """进程端到端：启动伪 ComfyUI → 收到就绪事件 → 停止。"""
    fake = TEST_DIR / "fake_comfy"
    fake.mkdir(exist_ok=True)
    port = 18288
    (fake / "main.py").write_text(
        "import sys, time\n"
        "def p(*a):\n"
        "    print(*a, flush=True)\n"
        "if '--help' in sys.argv:\n"
        "    p('usage: main.py [--port PORT] [--listen] [--force-fp16]')\n"
        "    sys.exit(0)\n"
        "p('Starting server')\n"
        f"p('To see the GUI go to: http://127.0.0.1:{port}')\n"
        "time.sleep(60)\n",
        encoding="utf-8")

    inst = Instance(name="fake", type="local", path=str(fake),
                    python=sys.executable)
    pm = ProcessManager()
    ready_url = []

    def on_ready(url):
        ready_url.append(url)

    pm.ready.connect(on_ready)
    launch = {"mode": "auto", "port": port, "listen": False,
              "auto_launch_browser": False, "force_fp16": False,
              "attention": "auto", "cuda_device": None,
              "extra_args": [], "auto_restart": False}

    try:
        pm.launch(inst, launch, {})
        # 等待 ready（最多 10 秒）
        loop = QEventLoop()
        pm.ready.connect(loop.quit)
        QTimer.singleShot(10000, loop.quit)
        loop.exec_()
        if ready_url and ready_url[0].endswith(str(port)):
            print("PM E2E OK: ready =", ready_url[0])
        else:
            print("PM E2E FAIL: no ready event")
            return False
        info = pm.running_info()
        if not info or info["pid"] <= 0:
            print("PM E2E FAIL: not running")
            return False
        pm.stop()
        time.sleep(0.6)
        if pm.is_running():
            print("PM E2E FAIL: still running after stop")
            return False
        print("PM E2E OK: stopped cleanly")
        return True
    finally:
        pm.shutdown()


def instance_add_probe(win):
    """模拟界面添加实例 → 触发各页签刷新（曾因 QComboBox.data 崩溃）。"""
    fake = TEST_DIR / "fake_add"
    fake.mkdir(exist_ok=True)
    (fake / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (fake / "comfy").mkdir(exist_ok=True)      # ComfyUI 特征目录
    (fake / "models").mkdir(exist_ok=True)
    win.instances_tab._add_by_path(str(fake))
    count = win.launch_tab.cb_instance.count()
    found = any(win.launch_tab.cb_instance.itemData(i) is not None
                for i in range(count))
    print(f"INSTANCE ADD OK (combo={count})" if found
          else "INSTANCE ADD FAIL")
    # 清理
    for it in win.inst_mgr.all():
        if it.path == str(fake):
            win.inst_mgr.remove(it.uid)
    win.instances_changed()


def version_list_probe(win):
    """用假数据填充版本列表，验证渲染与点击选择。"""
    t = win.update_tab
    t._info = {
        "current": "v0.3.29 (abc1234)",
        "git_install": True,
        "latest_tag": "v0.3.29",
        "latest_commit": "abc1234",
        "tags": [
            {"name": "v0.3.29", "commit": "abc1234", "date": "2026-01-01",
             "is_current": False},
            {"name": "v0.3.28", "commit": "def5678", "date": "2025-12-01",
             "is_current": True},
            {"name": "v0.3.27", "commit": "ghi9012", "date": None,
             "is_current": False},
        ],
        "branches": [],
    }
    t._selected = "v0.3.29"
    t._fill_lists()
    t.list_tags.setCurrentRow(1)   # 模拟点击 v0.3.28
    if t._selected == "v0.3.28" and t.list_tags.count() == 3:
        print("VERSION LIST OK")
    else:
        print(f"VERSION LIST FAIL selected={t._selected}")
    t._info = None
    t._selected = ""
    t.list_tags.clear()


def main():
    app = QApplication([])
    cfg = os.path.join(TEST_DIR, "smoke_config.json")
    win = MainWindow(config_path=cfg)
    win.show()

    steps = [0]

    def step():
        steps[0] += 1
        idx = steps[0]
        if idx < win.side.count():
            win.side.setCurrentRow(idx)
            QTimer.singleShot(150, step)
        else:
            dialog_probe(win)
            instance_add_probe(win)
            version_list_probe(win)
            ok = process_e2e(app)
            print("SMOKE OK: pages =", win.side.count(),
                  "| pm_e2e =", ok)
            app.quit()

    QTimer.singleShot(300, step)
    QTimer.singleShot(30000, app.quit)  # 兜底退出
    app.exec_()
    print("SMOKE DONE")


if __name__ == "__main__":
    main()
