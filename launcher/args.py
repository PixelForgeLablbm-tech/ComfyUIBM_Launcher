# -*- coding: utf-8 -*-
"""ComfyUI 启动参数构建与版本适配（无 UI 依赖，可独立测试）。"""
import subprocess
import time
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if __import__("os").name == "nt" else 0

MODES = [
    ("auto", "自动检测", "由 ComfyUI 自行决定显存策略"),
    ("lowvram", "低显存", "--lowvram 适合 ≤8G 显存"),
    ("normalvram", "标准", "默认行为，不传参（兼容所有版本）"),
    ("highvram", "高显存", "--highvram 适合大显存"),
    ("novram", "无显存限制", "--novram 全部加载到显存"),
    ("cpu", "纯 CPU", "--cpu 无显卡时使用"),
]
ATTENTIONS = [
    ("auto", "自动"),
    ("split", "Split (xformers)"),
    ("pytorch", "PyTorch 原生"),
]


def build_args(launch: dict, instance_extra_args: str = "") -> list:
    """由启动设置构建 ComfyUI 命令行参数。"""
    args = []
    if launch.get("listen"):
        args.append("--listen")
    args += ["--port", str(int(launch.get("port", 8188)))]
    mode = launch.get("mode", "auto")
    if mode == "lowvram":
        args.append("--lowvram")
    elif mode == "novram":
        args.append("--novram")
    elif mode == "highvram":
        args.append("--highvram")
    elif mode == "cpu":
        args.append("--cpu")
    # normalvram 在新版 ComfyUI 已移除，标准行为即为默认，不传参最兼容
    if launch.get("force_fp16"):
        args.append("--force-fp16")
    attn = launch.get("attention", "auto")
    if attn == "split":
        args.append("--use-split-cross-attention")
    elif attn == "pytorch":
        args.append("--use-pytorch-cross-attention")
    dev = launch.get("cuda_device")
    if dev is not None:
        args += ["--cuda-device", str(dev)]
    extra = list(launch.get("extra_args") or [])
    if instance_extra_args.strip():
        extra += instance_extra_args.split()
    for t in extra:
        t = t.strip()
        if t:
            args.append(t)
    return args


# ---------------------------------------------------------------- 参数适配
_ARGS_CACHE = {"key": None, "at": 0.0, "set": None}
_ARGS_CACHE_TTL = 60.0


def probe_supported_args(python: str, comfy_dir: Path):
    """跑一次 `main.py --help`，探测当前版本支持的启动参数（60s 缓存）。"""
    from . import git_utils
    try:
        head = git_utils.rev_parse_full(str(comfy_dir), "HEAD") or ""
    except Exception:
        head = ""
    key = f"{python}|{comfy_dir}|{head}"
    if _ARGS_CACHE["key"] == key and time.time() - _ARGS_CACHE["at"] < _ARGS_CACHE_TTL:
        return _ARGS_CACHE["set"]
    try:
        out = subprocess.run(
            [python, str(comfy_dir / "main.py"), "--help"],
            cwd=str(comfy_dir), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
        )
        if out.returncode != 0:
            return None
        tokens = set()
        for token in (out.stdout + out.stderr).split():
            if token.startswith("--"):
                tokens.add(token)
        if not tokens:
            return None
        _ARGS_CACHE.update(key=key, at=time.time(), set=tokens)
        return tokens
    except Exception:
        return None


def filter_unsupported(args, supported):
    """过滤掉当前版本不支持的参数，避免 "unrecognized arguments" 启动失败。"""
    out, dropped = [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if a in supported:
                out.append(a)
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    out.append(args[i + 1])
                    i += 1
            else:
                dropped.append(a)
        else:
            out.append(a)
        i += 1
    return out, dropped
