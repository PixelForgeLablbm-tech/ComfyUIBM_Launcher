# -*- coding: utf-8 -*-
"""对比各页按钮的高度与样式设置。"""
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

for f in ["ui/models_tab.py", "ui/update_tab.py", "ui/plugins_tab.py",
          "ui/instances_tab.py"]:
    t = (ROOT / f).read_text(encoding="utf-8")
    print("====", f)
    for m in re.finditer(r"QPushButton\(([^)]*)\)", t):
        line_no = t[:m.start()].count("\n") + 1
        seg = t[m.start():m.start() + 500]
        fh = re.search(r"setFixedHeight\((\d+)\)", seg)
        fw = re.search(r"setFixedSize\((\d+), (\d+)\)", seg)
        obj = re.search(r"setObjectName\(['\"]([\w]+)['\"]\)", seg)
        h = fw.group(2) if fw else (fh.group(1) if fh else "-")
        print(f"  L{line_no}: text={m.group(1)[:26]:28} height={h:>3} obj={obj.group(1) if obj else '-'}")
