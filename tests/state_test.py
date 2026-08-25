# -*- coding: utf-8 -*-
"""验证：移除实例后模型/插件页清空禁用，添加实例后恢复。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

QMessageBox.information = lambda *a, **k: QMessageBox.Ok
QMessageBox.warning = lambda *a, **k: QMessageBox.Ok
QMessageBox.critical = lambda *a, **k: QMessageBox.Ok
QMessageBox.question = lambda *a, **k: QMessageBox.Yes

from ui.main_window import MainWindow  # noqa: E402

TMP = ROOT / ".state_tmp"
TMP.mkdir(exist_ok=True)
fake = TMP / "fake_comfy"
fake.mkdir(parents=True, exist_ok=True)
(fake / "main.py").write_text("print('x')\n", encoding="utf-8")
(fake / "comfy").mkdir(exist_ok=True)
(fake / "models" / "loras").mkdir(parents=True, exist_ok=True)
(fake / "models" / "loras" / "a.safetensors").write_bytes(b"x")
(fake / "custom_nodes" / "plug_a").mkdir(parents=True, exist_ok=True)
(fake / "custom_nodes" / "plug_a" / "__init__.py").write_text("", encoding="utf-8")

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
    win = MainWindow(config_path=str(TMP / "cfg.json"))
    win.show()
    app.processEvents()

    # 1. 添加实例
    inst = win.inst_mgr.add_probe(str(fake))
    win.config.current_instance_id = inst.uid
    win.instances_changed(select_uid=inst.uid)
    app.processEvents()
    check("添加后模型页启用", win.models_tab.isEnabled() is True)
    check("添加后插件页启用", win.plugins_tab.isEnabled() is True)

    # 2. 移除实例（模拟界面移除流程）
    win.inst_mgr.remove(inst.uid)
    win.config.current_instance_id = None
    win.instances_changed()
    app.processEvents()
    check("移除后模型页禁用", win.models_tab.isEnabled() is False)
    check("移除后插件页禁用", win.plugins_tab.isEnabled() is False)
    check("移除后模型列表清空", win.models_tab.cat_list.count() == 0)

    # 3. 再次添加（模拟加回实例）
    inst2 = win.inst_mgr.add_probe(str(fake))
    win.config.current_instance_id = inst2.uid
    win.instances_changed(select_uid=inst2.uid)
    app.processEvents()
    check("重新添加后模型页恢复启用", win.models_tab.isEnabled() is True)
    check("重新添加后插件页恢复启用", win.plugins_tab.isEnabled() is True)

    win.pm.shutdown()
    print("==")
    print(f"STATE TEST: passed={passed} failed={failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
