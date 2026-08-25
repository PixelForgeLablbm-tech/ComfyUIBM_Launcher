# -*- coding: utf-8 -*-
"""镜像 / 代理 / GitHub 加速：生成 git 参数与子进程环境变量。"""

GH_PROXY_PRESETS = [
    ("gh-proxy.com（默认）", "https://gh-proxy.com/"),
    ("ghproxy.net", "https://ghproxy.net/"),
    ("ghfast.top", "https://ghfast.top/"),
    ("mirror.ghproxy.com", "https://mirror.ghproxy.com/"),
]

PYPI_MIRRORS = [
    ("aliyun", "阿里云", "https://mirrors.aliyun.com/pypi/simple/"),
    ("tsinghua", "清华", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("tencent", "腾讯", "https://mirrors.cloud.tencent.com/pypi/simple"),
    ("official", "官方", None),
]


def pypi_mirror_url(name: str):
    for key, _label, url in PYPI_MIRRORS:
        if key == name:
            return url
    return None


def proxy_env(mirrors: dict) -> dict:
    """代理开关关闭或地址为空时不设置任何代理变量（VPN 用户可直连）。"""
    env = {}
    if mirrors.get("use_proxy"):
        p = (mirrors.get("proxy") or "").strip()
        if p:
            env["HTTP_PROXY"] = p
            env["HTTPS_PROXY"] = p
            env["ALL_PROXY"] = p
    return env


def gh_rewrite_args(mirrors: dict) -> list:
    """GitHub 加速：生成 git 的 -c url.<prefix>https://github.com/.insteadOf 参数。

    只对本次命令生效，不修改全局 git 配置。
    """
    if not mirrors.get("gh_proxy"):
        return []
    base = (mirrors.get("gh_proxy_prefix") or "").strip().rstrip("/")
    if not base:
        return []
    return [
        "-c", f"url.{base}/https://github.com/.insteadOf=https://github.com/",
        "-c", f"url.{base}/https://github.com/.insteadOf=git@github.com:",
    ]


def gh_proxy_url(url: str, mirrors: dict) -> str:
    """GitHub 直链加速：https://github.com/... → https://<前缀>/https://github.com/...

    供 wheel 下载等场景使用（git 走 gh_rewrite_args）。
    """
    if not url.startswith("https://github.com/"):
        return url
    if not mirrors.get("gh_proxy"):
        return url
    base = (mirrors.get("gh_proxy_prefix") or "").strip().rstrip("/")
    if not base:
        return url
    return base + "/" + url


def git_extra_and_env(mirrors: dict):
    """返回 (git 前置 -c 参数列表, 环境变量 dict)，供 git 命令注入。"""
    return gh_rewrite_args(mirrors), proxy_env(mirrors)


def pip_env(mirrors: dict) -> dict:
    env = proxy_env(mirrors)
    if mirrors.get("hf_mirror"):
        env["HF_ENDPOINT"] = "https://hf-mirror.com"
    return env


def pip_index_args(mirrors: dict) -> list:
    url = pypi_mirror_url(mirrors.get("pypi_mirror", "official"))
    if url:
        return ["--index-url", url]
    return []
