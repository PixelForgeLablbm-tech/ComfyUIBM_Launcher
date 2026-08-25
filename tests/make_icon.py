# -*- coding: utf-8 -*-
"""把 F:\\ComfyUI启动器开发\\图标.png 转为多尺寸 .ico 并复制进项目 assets。"""
import shutil
from pathlib import Path

from PIL import Image

SRC = Path(r"F:\ComfyUI启动器开发\图标.png")
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)
ICO = ASSETS / "icon.ico"
PNG = ASSETS / "icon.png"

img = Image.open(SRC)
print("原图:", img.size, img.mode)

# 转 RGB(A)，统一 RGBA
if img.mode != "RGBA":
    img = img.convert("RGBA")

# 生成多尺寸 ico（16/24/32/48/64/128/256）
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(ICO, format="ICO", sizes=sizes)
# 同时存一张 256 png 供运行时加载
img.resize((256, 256), Image.LANCZOS).save(PNG, format="PNG")

print("ICO 已生成:", ICO, ICO.stat().st_size, "bytes")
print("PNG 已生成:", PNG)
