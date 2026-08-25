# -*- coding: utf-8 -*-
"""下载并解压 GitHub CLI（gh）到 .gh_cli/ 目录。"""
import io
import shutil
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

ROOT = Path(__file__).resolve().parent.parent
GH_CLI_DIR = ROOT / ".gh_cli"
GH_CLI_DIR.mkdir(exist_ok=True)
PROXY = "https://gh-proxy.com/"


def get(url, **kw):
    return requests.get(url, timeout=60, headers={
        "User-Agent": "ComfyUIBM-Launcher"}, **kw)


def main():
    # 1. 查最新版本
    api = f"{PROXY}https://api.github.com/repos/cli/cli/releases/latest"
    r = get(api)
    if r.status_code != 200:
        print(f"查询版本失败: {r.status_code}")
        sys.exit(1)
    tag = r.json()["tag_name"]
    print("gh 最新版本:", tag)

    # 2. 找 windows_amd64 zip 资产
    asset = None
    for a in r.json().get("assets", []):
        name = a["name"]
        if "windows_amd64.zip" in name and "windows_arm" not in name:
            asset = a
            break
    if not asset:
        print("未找到 Windows 资产")
        sys.exit(1)
    print("资产:", asset["name"])

    # 3. 下载（走镜像）
    url = f"{PROXY}{asset['browser_download_url']}"
    print("下载中…")
    rr = get(url, stream=True)
    if rr.status_code != 200:
        print(f"下载失败: {rr.status_code}")
        sys.exit(1)
    data = rr.content
    print(f"已下载 {len(data) / 1024 / 1024:.1f} MB")

    # 4. 解压
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(GH_CLI_DIR)
    exe = next(GH_CLI_DIR.rglob("gh.exe"), None)
    if not exe:
        print("解压后未找到 gh.exe")
        sys.exit(1)
    print("gh 已安装:", exe)


if __name__ == "__main__":
    main()
