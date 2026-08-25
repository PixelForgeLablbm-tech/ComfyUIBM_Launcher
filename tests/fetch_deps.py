# -*- coding: utf-8 -*-
"""手动下载并解压依赖轮子到 .smoke_deps2（绕过 pip 解包）。

用法: python tests/fetch_deps.py
"""
import json
import os
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / ".wheels2"
TARGET = ROOT / ".smoke_deps2"
WHEELS.mkdir(exist_ok=True)
TARGET.mkdir(exist_ok=True)

# (包名, 版本或 None 用最新)
PKGS = [
    ("PyQt5", "5.15.11"),
    ("PyQt5-Qt5", "5.15.2"),
    ("PyQt5-sip", "12.19.0"),
    ("requests", None),
    ("urllib3", None),
    ("idna", None),
    ("charset-normalizer", None),
    ("certifi", None),
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def fetch(url: str, dest: Path):
    print(f"download: {dest.name} <- {url.split('/')[-1]}")
    with urllib.request.urlopen(url, timeout=180, context=ctx) as r, \
            open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)


def pick_wheel(name: str, version):
    url = f"https://pypi.org/pypi/{name}/{version}/json" if version \
        else f"https://pypi.org/pypi/{name}/json"
    with urllib.request.urlopen(url, timeout=60, context=ctx) as r:
        data = json.loads(r.read().decode("utf-8"))
    files = data["urls"]
    my_cp = f"cp{sys.version_info.major}{sys.version_info.minor}"

    if name == "PyQt5":
        # 本体：平台 + abi3
        plat = ("win_amd64" if os.name == "nt"
                else ("macosx" if sys.platform == "darwin" else "manylinux"))
        cands = [f for f in files
                 if plat in f["filename"] and "abi3" in f["filename"]]
    elif name == "PyQt5-sip":
        plat = "win_amd64" if os.name == "nt" else \
            ("macosx" if sys.platform == "darwin" else "manylinux")
        cps = [f for f in files if plat in f["filename"]]
        cands = [f for f in cps if my_cp in f["filename"]] or cps
    elif name == "PyQt5-Qt5":
        plat = "win_amd64" if os.name == "nt" else \
            ("macosx" if sys.platform == "darwin" else "manylinux")
        cands = [f for f in files if f["filename"].endswith(f"{plat}.whl")]
    else:
        cands = [f for f in files if f["filename"].endswith("py3-none-any.whl")]

    if not cands:
        raise RuntimeError(
            f"no wheel for {name}: {[x['filename'] for x in files]}")
    f = cands[0]
    return f["filename"], data["info"]["version"], f["url"]


def main():
    for name, version in PKGS:
        fn, ver, url = pick_wheel(name, version)
        dest = WHEELS / fn
        if not dest.exists():
            fetch(url, dest)
        with zipfile.ZipFile(dest) as z:
            z.extractall(TARGET)
        print(f"  extracted {fn} (v{ver})")
    print("DEPS READY:", TARGET)


if __name__ == "__main__":
    main()
