# -*- coding: utf-8 -*-
"""启动器自身更新检查：对比 GitHub Releases 最新版本。"""
import re

import requests

# 你的 GitHub 用户名 / 仓库名
APP_REPO = "PixelForgeLablbm-tech/ComfyUIBM_Launcher"


def _parse_version(v: str):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def has_update(current: str, latest_tag: str) -> bool:
    """latest_tag 是否比 current 新。无法解析时按字符串不同判断。"""
    c = _parse_version(current)
    l = _parse_version(latest_tag)
    if c is None or l is None:
        return bool(latest_tag) and latest_tag != current
    return l > c


def _proxies(mirrors: dict):
    if (mirrors or {}).get("use_proxy"):
        p = (mirrors.get("proxy") or "").strip()
        if p:
            return {"http": p, "https": p}
    return None


def check_latest(mirrors: dict = None):
    """查询 GitHub Releases 最新版，返回 dict(latest_tag/name/html_url/assets)。

    assets: 该 Release 的资产列表 [{name, browser_download_url}]。
    直连失败时若开启 GitHub 加速则走镜像重试；全部失败抛 RuntimeError。
    """
    path = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
    urls = [path]
    if (mirrors or {}).get("gh_proxy"):
        prefix = (mirrors.get("gh_proxy_prefix") or "").strip().rstrip("/")
        if prefix:
            urls.append(f"{prefix}/{path}")

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ComfyUIBM-Launcher",
    }
    last_err = None
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers=headers,
                             proxies=_proxies(mirrors))
            if r.status_code == 200:
                d = r.json()
                assets = [{"name": a.get("name", ""),
                           "browser_download_url": a.get("browser_download_url", "")}
                          for a in d.get("assets", [])]
                return {
                    "latest_tag": d.get("tag_name") or "",
                    "name": d.get("name") or "",
                    "html_url": d.get("html_url") or "",
                    "assets": assets,
                }
            if r.status_code == 404:
                last_err = RuntimeError(
                    "仓库或 Releases 不存在，请先在 GitHub 发布一个版本")
            elif r.status_code == 403:
                last_err = RuntimeError("GitHub API 限流，请稍后再试")
            else:
                last_err = RuntimeError(f"GitHub API 返回 {r.status_code}")
        except requests.RequestException as e:
            last_err = RuntimeError(f"网络错误：{e}")
    raise last_err or RuntimeError("无法访问 GitHub API")


def asset_url(info: dict, name: str):
    """按资产名取下载地址。"""
    for a in info.get("assets", []):
        if a.get("name") == name:
            return a.get("browser_download_url")
    return None


def download(url: str, dest, mirrors: dict = None, progress=None):
    """流式下载到 dest；progress(done_bytes, total_bytes) 回调。

    直连失败时若开启 GitHub 加速则走镜像重试（与 check_latest 一致）。
    """
    mirrors = mirrors or {}
    proxies = _proxies(mirrors)
    urls = [url]
    if url.startswith("https://github.com/"):
        prefix = (mirrors.get("gh_proxy_prefix") or "").strip().rstrip("/")
        if mirrors.get("gh_proxy") and prefix:
            urls.append(f"{prefix}/{url}")

    headers = {"User-Agent": "ComfyUIBM-Launcher"}
    last_err = None
    for u in urls:
        try:
            with requests.get(u, stream=True, timeout=60, proxies=proxies,
                              headers=headers) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                done = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
            return dest
        except requests.RequestException as e:
            last_err = e
            continue
    raise last_err or RuntimeError(f"下载失败: {url}")
