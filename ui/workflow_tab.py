# -*- coding: utf-8 -*-
"""工作流识别页签（占位）：识别 / 分类 / 管理 ComfyUI 工作流文件。"""
from PyQt5.QtWidgets import (
    QGroupBox, QLabel, QVBoxLayout, QWidget,
)


class WorkflowTab(QWidget):
    """工作流识别（功能开发中）。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(14)

        card = QGroupBox("工作流识别")
        v = QVBoxLayout(card)
        v.setSpacing(8)
        tip = QLabel("识别 / 分类 / 管理 ComfyUI 工作流文件（功能开发中，敬请期待）。")
        tip.setProperty("dim", True)
        tip.setWordWrap(True)
        v.addWidget(tip)
        lay.addWidget(card)
        lay.addStretch(1)

    # ------------------------------------------------------------ 数据
    def reload(self):
        """页面切换时调用（预留）。"""
        pass
