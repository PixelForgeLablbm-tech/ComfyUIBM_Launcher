# -*- coding: utf-8 -*-
"""GitHub 插件搜索：按名称搜索 ComfyUI 插件仓库。"""
from urllib.parse import quote

import requests

# 知名 ComfyUI 节点作者（官方/高认可度），搜索结果显示「官方」徽标
OFFICIAL_AUTHORS = {
    "comfy-org",         # ComfyUI-Manager 官方组织
    "ltdrdata",          # ComfyUI-Manager 原作者 / Inspect / Animation
    "comfyanonymous",    # ComfyUI 本体作者
    "Kosinkadink",       # VideoHelperSuite / ControlNet
    "cubiq",             # IPAdapter / AnimateDiff-Evolved
    "kijai",             # 各种加速节点
    "ssitu",             # ComfyUI_UltimateSDUpscale
    "city96",            # ComfyUI-GGUF
    "Fannovel16",        # ComfyUI-VideoHelperSuite 维护 / Frame Interpolation
    "pythongosssss",     # CustomScripts / Subgraph
    "rgthree",           # rgthree-comfy
    "WASasquatch",       # WAS Node Suite
    "chrisgoringe",      # cg-use-everywhere
    "BlenderNeko",       # ComfyUI_TiledKSampler
    "Gourieff",          # ComfyUI-ReActor
    "ZHO-ZHO-ZHO",       # ComfyUI-PhotoMaker 等
    "jags111",           # Efficiency Nodes
    "crystian",          # ComfyUI-Crystools
    "sipherxyz",         # ComfyUI-Image-Selector
    "melMass",           # ComfyUI-MotionDiff
    "akatzai",           # ComfyUI-Custom-Scripts 相关
}


def is_official_author(owner: str) -> bool:
    return (owner or "").lower() in OFFICIAL_AUTHORS


def _gh_prefix_url(mirrors: dict, url: str) -> str:
    """若开启 GitHub 加速，生成经镜像前缀访问的 URL。"""
    if not (mirrors or {}).get("gh_proxy"):
        return url
    prefix = (mirrors.get("gh_proxy_prefix") or "").strip().rstrip("/")
    if not prefix:
        return url
    return f"{prefix}/{url}"


def _proxies(mirrors: dict):
    if (mirrors or {}).get("use_proxy"):
        p = (mirrors.get("proxy") or "").strip()
        if p:
            return {"http": p, "https": p}
    return None


def search_repos(query: str, mirrors: dict = None, per_page: int = 10):
    """按名称搜索 GitHub 仓库，返回 items 列表。

    直连失败时若开启了 GitHub 加速则自动走镜像前缀重试。
    网络全部失败时抛 RuntimeError。
    """
    query = query.strip()
    if not query:
        raise RuntimeError("请输入插件名称")
    q = quote(query)
    # 限定 ComfyUI 生态：全文同时匹配关键词与 comfyui（按 star 排序）
    path = (f"https://api.github.com/search/repositories?"
            f"q={q}+comfyui&sort=stars&order=desc&per_page={per_page}")
    candidates = [path]
    if (mirrors or {}).get("gh_proxy"):
        candidates.append(_gh_prefix_url(mirrors, path))

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ComfyUI-Launcher",
    }
    last_err = None
    for url in candidates:
        try:
            r = requests.get(url, timeout=20, headers=headers,
                             proxies=_proxies(mirrors))
            if r.status_code == 200:
                return r.json().get("items", [])
            if r.status_code == 403:
                last_err = RuntimeError(
                    "GitHub API 限流（每分钟 10 次），请稍后再试")
            elif r.status_code == 404:
                last_err = RuntimeError("GitHub API 地址不可用")
            else:
                last_err = RuntimeError(f"GitHub API 返回 {r.status_code}")
        except requests.RequestException as e:
            last_err = RuntimeError(f"网络错误：{e}")
    raise last_err or RuntimeError("搜索失败：无法访问 GitHub API")
