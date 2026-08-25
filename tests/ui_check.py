# -*- coding: utf-8 -*-
"""UI 遮挡自检：离屏渲染真实页面，检查表格内按钮是否被单元格裁切。

用法: python tests/ui_check.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox

QMessageBox.information = lambda *a, **k: QMessageBox.Ok
QMessageBox.warning = lambda *a, **k: QMessageBox.Ok
QMessageBox.critical = lambda *a, **k: QMessageBox.Ok
QMessageBox.question = lambda *a, **k: QMessageBox.Yes

from ui.main_window import MainWindow  # noqa: E402
from launcher import model_manager, plugin_manager  # noqa: E402

TEST = ROOT / ".ui_check_tmp"
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

problems = 0


def check_table(tbl, name):
    global problems
    for row in range(tbl.rowCount()):
        row_h = tbl.rowHeight(row)
        for col in range(tbl.columnCount()):
            w = tbl.cellWidget(row, col)
            if w is None:
                continue
            rect = tbl.visualRect(tbl.model().index(row, col))
            if rect.width() <= 1 or rect.height() <= 1:
                continue
            gw = w.geometry()
            ok = (gw.top() >= rect.top() - 1 and gw.bottom() <= rect.bottom() + 1 and
                  gw.left() >= rect.left() - 1 and gw.right() <= rect.right() + 1)
            mark = "OK  " if ok else "CLIP"
            if not ok:
                problems += 1
            print(f"[{mark}] {name} r{row}c{col} widget={gw} cell={rect} rowH={row_h}")


def main():
    app = QApplication([])
    win = MainWindow(config_path=str(TEST / "cfg.json"))
    win.show()
    app.processEvents()

    # 添加假实例并设为当前
    inst = win.inst_mgr.add_probe(str(fake))
    win.config.current_instance_id = inst.uid
    win.config.save()
    win.instances_changed()
    app.processEvents()
    print("== 实例管理 ==")
    check_table(win.instances_tab.table_configured, "已配置")

    # 模型页：同步喂扫描结果
    summary = model_manager.category_summary(str(fake))
    win.models_tab._on_scanned(summary)
    app.processEvents()
    print("== 模型管理 ==")
    check_table(win.models_tab.table, "模型")

    # 插件页：同步喂扫描结果
    plugins = plugin_manager.scan_plugins(str(fake))
    win.plugins_tab._fill(plugins)
    app.processEvents()
    print("== 插件管理 ==")
    check_table(win.plugins_tab.table, "插件")

    print("==")
    print("UI CHECK: clipped =", problems)
    win.pm.shutdown()
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
