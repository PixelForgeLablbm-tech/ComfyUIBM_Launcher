# -*- coding: utf-8 -*-
"""ComfyUI HTTP API 客户端（用于远程实例状态检测）。"""
import requests


def normalize_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def system_stats(url: str, timeout: float = 5.0) -> dict:
    """探测实例是否在线，返回 /system_stats 的 JSON。"""
    base = normalize_url(url)
    if not base:
        raise ValueError("地址为空")
    r = requests.get(base + "/system_stats", timeout=timeout)
    r.raise_for_status()
    return r.json()


def is_online(url: str, timeout: float = 4.0) -> bool:
    try:
        system_stats(url, timeout=timeout)
        return True
    except Exception:
        return False
