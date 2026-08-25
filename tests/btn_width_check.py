# -*- coding: utf-8 -*-
"""离屏验证：单元格按钮宽度足够容纳文字（不截断）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from ui.models_tab import _cell_button
from ui.instances_tab import _cell_button as ib
from ui.plugins_tab import _cell_button as pb

fails = 0
for maker, texts in (
    (_cell_button, ["所在目录", "删除"]),
    (ib, ["设为当前", "编辑", "移除", "添加"]),
    (pb, ["更新", "目录"]),
):
    for t in texts:
        btn = maker(t, "ghost", lambda: None)
        fm = btn.fontMetrics()
        need = fm.horizontalAdvance(t)
        avail = btn.width() - 14   # 减去左右 padding(6*2) + 边框(1*2)
        ok = avail >= need
        if not ok:
            fails += 1
        print(f"[{'OK' if ok else 'FAIL'}] '{t}' 按钮宽={btn.width()} "
              f"文字需={need} 可用={avail}")

print("\n结果:", "全部通过" if fails == 0 else f"{fails} 个失败")
sys.exit(1 if fails else 0)
