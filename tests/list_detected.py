# -*- coding: utf-8 -*-
"""列出本机扫描到的 ComfyUI 安装。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from launcher.config import Config
from launcher.instance_scanner import detect_instances

cfg = Config()
found = detect_instances(cfg)
print(f"共发现 {len(found)} 个 ComfyUI 安装:")
for f in found:
    print(f"  - {f['name']}")
    print(f"    路径: {f['path']}")
    print(f"    版本: {f.get('version') or '未知'}")
    print(f"    Python: {'已自动找到' if f.get('python') else '未找到'}")
