# -*- coding: utf-8 -*-
"""全按钮映射测试：离屏遍历所有页面按钮，检查信号连接并模拟点击。

覆盖：启动/实例/模型/插件/更新/设置页 + 表格行内按钮 + 日志面板。
副作用函数（进程启动、文件对话框、打开资源管理器、git 操作、模态对话框）均打桩，
只验证信号链路与点击不崩溃。

用法: python tests/button_test.py
"""
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog,
                             QMessageBox, QPushButton)
# ---------------- 副作用打桩 ----------------
QMessageBox.information = lambda *a, **k: QMessageBox.Ok
QMessageBox.warning = lambda *a, **k: QMessageBox.Ok
QMessageBox.critical = lambda *a, **k: QMessageBox.Ok
QMessageBox.question = lambda *a, **k: QMessageBox.Yes
QMessageBox.about = lambda *a, **k: QMessageBox.Ok
# 标题栏关闭按钮会触发 closeEvent 里的模态确认框，打桩避免挂起
QMessageBox.exec_ = lambda self: QMessageBox.Rejected
# 声明对话框等模态对话框也打桩
QDialog.exec_ = lambda self: QDialog.Rejected
QFileDialog.getOpenFileNames = lambda *a, **k: ([], "")
QFileDialog.getExistingDirectory = lambda *a, **k: ""
QFileDialog.getOpenFileName = lambda *a, **k: ("", "")

from ui.dialogs import InstanceDialog, PluginInstallDialog  # noqa: E402
InstanceDialog.exec_ = lambda self: QDialog.Rejected
PluginInstallDialog.exec_ = lambda self: QDialog.Rejected

from ui import dialogs  # noqa: E402
dialogs.open_in_explorer = lambda *a, **k: None

from ui.main_window import MainWindow  # noqa: E402
from launcher import plugin_manager, updater, model_manager  # noqa: E402

# 网络 / 进程 / 文件操作桩
updater.list_versions = lambda *a, **k: (_ for _ in ()).throw(
    RuntimeError("stub: 网络"))
updater.update_to = lambda *a, **k: (_ for _ in ()).throw(
    RuntimeError("stub: 网络"))
updater.install_requirements = lambda *a, **k: (_ for _ in ()).throw(
    RuntimeError("stub: 网络"))
plugin_manager.clone_plugin = lambda *a, **k: (_ for _ in ()).throw(
    RuntimeError("stub: git"))
plugin_manager.update_plugin = lambda *a, **k: None
plugin_manager.install_requirements = lambda *a, **k: "stub ok"
plugin_manager.toggle_plugin = lambda *a, **k: None
plugin_manager.remove_plugin = lambda *a, **k: None
model_manager.import_models = lambda *a, **k: (0, 0, [])
import ui.models_tab as _mt
_mt.os.remove = lambda *a, **k: None

TEST = ROOT / ".btn_tmp"
TEST.mkdir(exist_ok=True)
fake = TEST / "fake_comfy"
fake.mkdir(parents=True, exist_ok=True)
(fake / "main.py").write_text("print('x')\n", encoding="utf-8")
(fake / "comfy").mkdir(exist_ok=True)
(fake / "models" / "loras").mkdir(parents=True, exist_ok=True)
(fake / "models" / "loras" / "a.safetensors").write_bytes(b"x" * 10)
(fake / "models" / "checkpoints").mkdir(parents=True, exist_ok=True)
(fake / "models" / "checkpoints" / "big.ckpt").write_bytes(b"y" * 10)
(fake / "custom_nodes" / "plug_a").mkdir(parents=True, exist_ok=True)
(fake / "custom_nodes" / "plug_a" / "__init__.py").write_text("", encoding="utf-8")
(fake / "custom_nodes" / "plug_b").mkdir(parents=True, exist_ok=True)
(fake / "custom_nodes" / "plug_b" / "requirements.txt").write_text("", encoding="utf-8")

results = []


def page_name(btn):
    """按钮所在页面名（父链向上找 QStackedWidget 的页索引）。"""
    from PyQt5.QtWidgets import QStackedWidget
    w = btn.parent()
    while w is not None:
        if isinstance(w, QStackedWidget):
            return f"page{w.currentIndex()}"
        w = w.parent()
    return "other"


def main():
    app = QApplication([])
    win = MainWindow(config_path=str(TEST / "cfg.json"))
    win.show()
    app.processEvents()

    # 添加假实例并设为当前（触发各页刷新）
    inst = win.inst_mgr.add_probe(str(fake))
    win.config.current_instance_id = inst.uid
    win.config.save()
    win.instances_changed()
    app.processEvents()

    # 填充各页数据，让行内按钮出现
    win.instances_tab._on_scanned([
        {"uid": "x1", "name": "已装实例", "path": str(fake),
         "version": "v1", "python": "py"},
        {"uid": "x2", "name": "新发现", "path": str(fake) + "2",
         "version": "v2", "python": ""},
    ])
    summary = model_manager.category_summary(str(fake))
    win.models_tab._on_scanned(summary)
    plugins = plugin_manager.scan_plugins(str(fake))
    win.plugins_tab._fill(plugins)
    win.update_tab._info = {
        "current": "v1", "git_install": True, "latest_tag": "v2",
        "latest_commit": "abc", "tags": [
            {"name": "v2", "commit": "abc", "date": "2026-01-01",
             "is_current": False},
        ], "branches": [],
    }
    win.update_tab._selected = "v2"
    win.update_tab._fill_lists()
    app.processEvents()

    # 遍历所有按钮
    buttons = win.findChildren(QPushButton)
    tested = skipped = 0
    for btn in list(buttons):
        # 点击会触发页面刷新（重建 cellWidget），旧按钮可能已被 Qt 删除
        try:
            label = btn.text().strip() or btn.objectName() or "?"
            enabled = btn.isEnabled()
        except RuntimeError:
            continue
        if not enabled:
            skipped += 1
            results.append(f"SKIP(disabled) {label} @ {page_name(btn)}")
            continue
        n = btn.receivers(btn.clicked)
        try:
            btn.click()
            if n == 0:
                results.append(f"FAIL no-connect {label} @ {page_name(btn)}")
            else:
                results.append(f"OK {label} @ {page_name(btn)} (conn={n})")
            tested += 1
        except RuntimeError:
            results.append(f"SKIP deleted-after-click {label}")
        except Exception as e:
            results.append(f"FAIL click-exc {label} @ {page_name(btn)}: {e}")
            tested += 1
        app.processEvents()

    # 额外交互：版本列表点击、分类点击、下拉切换
    try:
        if win.update_tab.list_tags.count():
            win.update_tab.list_tags.setCurrentRow(0)
        if win.models_tab.cat_list.count():
            win.models_tab.cat_list.setCurrentRow(0)
        win.launch_tab.cb_mode.setCurrentIndex(1)
        win.launch_tab.cb_gpu.setCurrentIndex(0)
        results.append("OK extra-interactions")
    except Exception as e:
        results.append(f"FAIL extra-interactions: {e}")

    win.pm.shutdown()
    report = "\n".join(results)
    (ROOT / "tests" / "btn_report.txt").write_text(report, encoding="utf-8")
    for r in results:
        print(r)
    fails = [r for r in results if r.startswith("FAIL")]
    print("==")
    print(f"BUTTON TEST: total={tested} skipped={skipped} fails={len(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
