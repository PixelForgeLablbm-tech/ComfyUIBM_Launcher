# -*- coding: utf-8 -*-
"""实例自动扫描与探测：发现本机所有 ComfyUI 安装。"""
import os
import uuid
from pathlib import Path

from . import git_utils


def _new_uid() -> str:
    return uuid.uuid4().hex[:12]


def is_comfyui_dir(d: Path) -> bool:
    """判定一个目录是否是 ComfyUI 根目录。

    仅含 main.py 不够（其他项目也可能有 main.py，如本启动器自身），
    需要同时具备 ComfyUI 特征目录（comfy 核心包 / models / custom_nodes）。
    """
    if not d.joinpath("main.py").exists():
        return False
    for marker in ("comfy", "models", "custom_nodes"):
        if d.joinpath(marker).exists():
            return True
    return False


def find_python(comfy_dir: Path):
    """按常见布局探测 Python 可执行文件（含秋叶整合包父目录布局）。"""
    candidates = [
        comfy_dir / "python_embeded" / "python.exe",
        comfy_dir / "python" / "python.exe",
        comfy_dir / "venv" / "Scripts" / "python.exe",
        comfy_dir / ".venv" / "Scripts" / "python.exe",
    ]
    parent = comfy_dir.parent
    if parent:
        candidates += [
            parent / "python" / "python.exe",
            parent / "python_embeded" / "python.exe",
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def probe(path: str) -> dict:
    """探测一个 ComfyUI 目录，返回实例 dict；校验失败抛异常。"""
    p = Path(path)
    if not p.joinpath("main.py").exists():
        raise ValueError(f"目录中没有 main.py：{p}")
    if not is_comfyui_dir(p):
        raise ValueError(
            f"该目录不是 ComfyUI 根目录：{p}\n"
            "缺少 ComfyUI 特征目录（comfy / models / custom_nodes）。\n"
            "请选择包含 main.py、comfy、models 的 ComfyUI 根目录。")
    python = find_python(p)
    name = p.name or "ComfyUI"
    return {
        "uid": _new_uid(),
        "name": name,
        "type": "local",
        "path": str(p),
        "url": "",
        "python": python or "",
        "launch_args": "",
        "notes": "",
    }


def detect_instances(cfg) -> list:
    """扫描常见位置，找出所有 ComfyUI 安装（去重，按名称排序）。

    返回 list[dict]：name / path / version / python / uid。
    """
    roots = []
    for inst in cfg.instances:
        p = Path(inst.get("path") or "")
        if p.parent.exists():
            roots.append(p.parent)
        if p.exists():
            roots.append(p)

    for drive in ("C:", "D:", "E:", "F:", "G:"):
        root = Path(f"{drive}\\")
        if root.exists():
            roots.append(root)
    home = os.environ.get("USERPROFILE")
    if home:
        roots.append(Path(home))

    seen = set()
    found = []

    def push_if_new(dir_path: Path):
        key = str(dir_path).lower()
        if key in seen:
            return
        seen.add(key)
        version = ""
        if git_utils.has_own_git_dir(dir_path):
            version = git_utils.describe(dir_path)  # 标签名
            if not version:
                version = git_utils.short_commit(dir_path) or ""
        found.append({
            "uid": _new_uid(),
            "name": dir_path.name or "ComfyUI",
            "path": str(dir_path),
            "version": version,
            "python": find_python(dir_path) or "",
        })

    for root in roots:
        try:
            entries = [e for e in root.iterdir() if e.is_dir()]
        except OSError:
            continue
        for d in entries:
            if is_comfyui_dir(d):
                push_if_new(d)
            # 子目录含 main.py（如 E:\ComfyUI\ComfyUI-aki-v3\ComfyUI）
            try:
                for sub in d.iterdir():
                    if sub.is_dir() and is_comfyui_dir(sub):
                        push_if_new(sub)
            except OSError:
                continue

    found.sort(key=lambda x: x["name"].lower())
    return found
