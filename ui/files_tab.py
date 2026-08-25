# -*- coding: utf-8 -*-
"""文件管理页签：一键打开当前实例的常用目录。"""
from pathlib import Path

from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from ui.dialogs import open_in_explorer


class FilesTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(12)

        card = QGroupBox("文件管理（当前实例）")
        v = QVBoxLayout(card)
        v.setSpacing(8)
        self.lb_hint = QLabel("请先在「实例管理」中选择一个本地实例。")
        self.lb_hint.setProperty("dim", True)
        v.addWidget(self.lb_hint)

        self._rows = {}
        for key, label, desc in [
            ("root", "打开根目录", "ComfyUI 安装根目录"),
            ("workflows", "打开工作流", "保存的工作流目录"),
            ("custom_nodes", "打开自定义节点", "custom_nodes 插件目录"),
            ("input", "打开输入图片", "input 输入目录"),
            ("output", "打开输出图片", "output 输出目录"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(10)
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(150)
            btn.clicked.connect(
                lambda _=False, k=key: self._open_dir(k))
            path_lb = QLabel("—")
            path_lb.setProperty("dim", True)
            row.addWidget(btn)
            row.addWidget(path_lb, 1)
            v.addLayout(row)
            self._rows[key] = (btn, path_lb, desc)

        tip = QLabel("点击按钮在系统文件管理器中打开对应目录。")
        tip.setProperty("dim", True)
        v.addWidget(tip)
        lay.addWidget(card)
        lay.addStretch(1)

    # ------------------------------------------------------------ 数据
    def reload(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            for _btn, lb, _d in self._rows.values():
                lb.setText("—")
            self.lb_hint.setText("请先在「实例管理」中选择一个本地实例。")
            for btn, _lb, _d in self._rows.values():
                btn.setEnabled(False)
            return
        self.lb_hint.setText(
            f"实例：{inst.name}　{inst.path}")
        for btn, lb, _d in self._rows.values():
            btn.setEnabled(True)
        for key, (_btn, lb, _d) in self._rows.items():
            lb.setText(str(self._resolve(key, inst)))

    def _resolve(self, key, inst) -> Path:
        root = Path(inst.path)
        if key == "root":
            return root
        if key == "workflows":
            for p in (root / "user" / "default" / "workflows",
                      root / "user" / "workflows",
                      root / "user"):
                if p.is_dir():
                    return p
            return root / "user" / "default" / "workflows"
        if key == "custom_nodes":
            return root / "custom_nodes"
        if key == "input":
            return root / "input"
        if key == "output":
            return root / "output"
        return root

    # ------------------------------------------------------------ 操作
    def _open_dir(self, key):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(self, "提示", "请先在「实例管理」中选择一个本地实例")
            return
        d = self._resolve(key, inst)
        if not d.exists():
            _btn, _lb, desc = self._rows[key]
            QMessageBox.information(
                self, "目录不存在",
                f"{desc}目录还不存在：\n{d}\n\n"
                + ("请先在 ComfyUI 中保存至少一个工作流。"
                   if key == "workflows" else
                   "目录会在 ComfyUI 运行时自动创建。"))
            return
        open_in_explorer(self, str(d))
