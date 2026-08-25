# -*- coding: utf-8 -*-
"""上传资产到 GitHub Release。

用法: python tools/upload_asset.py --token ghp_xxx --tag v1.0.0 --file dist\\ComfyUIBM_Launcher.exe
"""
import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

USER = "PixelForgeLablbm-tech"
REPO = "ComfyUIBM_Launcher"
API = "https://api.github.com"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--tag", default="v1.0.0")
    ap.add_argument("--file", required=True)
    args = ap.parse_args()

    f = Path(args.file)
    if not f.exists():
        print("文件不存在:", f)
        sys.exit(1)

    headers = {"Authorization": f"token {args.token}",
               "Accept": "application/vnd.github+json",
               "User-Agent": "ComfyUIBM-Launcher"}

    # 按 tag 找 release
    r = requests.get(f"{API}/repos/{USER}/{REPO}/releases/tags/{args.tag}",
                     headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"找不到 Release {args.tag}: {r.status_code}")
        sys.exit(1)
    upload_url = r.json()["upload_url"].split("{")[0]   # uploads.github.com 端点

    # 上传资产
    with open(f, "rb") as fh:
        r = requests.post(
            f"{upload_url}?name={f.name}",
            headers={**headers, "Content-Type": "application/octet-stream"},
            data=fh, timeout=600)
    if r.status_code not in (200, 201):
        print(f"上传失败: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    print(f"✔ 已上传资产: {f.name} -> {args.tag}")


if __name__ == "__main__":
    main()
