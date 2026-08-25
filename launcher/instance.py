# -*- coding: utf-8 -*-
"""实例数据模型与本地/远程实例辅助函数。"""
import os
import re
import subprocess
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import git_utils

TYPE_LOCAL = "local"
TYPE_REMOTE = "remote"


def _new_uid() -> str:
    return uuid.uuid4().hex[:12]


def detect_portable_python(root: Path) -> str:
    """ComfyUI 便携版常见位置：python_embeded/python.exe 或 venv。"""
    candidates = [
        root / "python_embeded" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return ""


@dataclass
class Instance:
    uid: str = field(default_factory=_new_uid)
    name: str = ""
    type: str = TYPE_LOCAL
    path: str = ""                 # 本地实例根目录
    url: str = ""                  # 远程实例地址，如 http://127.0.0.1:8188
    python: str = ""               # 该实例使用的 Python；为空则用全局设置
    launch_args: str = ""
    notes: str = ""

    # ---------- 序列化 ----------
    @classmethod
    def from_dict(cls, d: dict) -> "Instance":
        known = set(cls.__dataclass_fields__)
        data = {k: v for k, v in d.items() if k in known}
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)

    # ---------- 属性 ----------
    @property
    def is_local(self) -> bool:
        return self.type == TYPE_LOCAL

    @property
    def root(self) -> Path:
        return Path(self.path) if self.path else Path()

    def main_py(self) -> Path:
        return self.root / "main.py"

    def valid_local(self) -> bool:
        return self.is_local and self.main_py().exists()

    def resolve_python(self, fallback: str) -> str:
        return self.python or detect_portable_python(self.root) or fallback or "python"

    def describe(self) -> str:
        return str(self.root) if self.is_local else (self.url or "")

    # ---------- 版本信息 ----------
    def version_info(self) -> dict:
        """返回 dict: describe / branch / commit / remote / is_git / exists。"""
        if not self.is_local or not self.root.exists():
            return {"describe": "", "branch": "", "commit": "",
                    "remote": "", "is_git": False, "exists": False}
        is_git = git_utils.is_git_repo(self.root)
        desc = git_utils.describe(self.root) if is_git else self._pyproject_version()
        return {
            "describe": desc,
            "branch": git_utils.current_branch(self.root) or "",
            "commit": git_utils.short_commit(self.root) or "",
            "remote": git_utils.remote_url(self.root) or "",
            "is_git": is_git,
            "exists": True,
        }

    def _pyproject_version(self) -> str:
        f = self.root / "pyproject.toml"
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
            if m:
                return "v" + m.group(1)
        except Exception:
            pass
        return ""

    # ---------- 启动 / 停止 ----------
    def launch(self, python_exe: str, args: str) -> subprocess.Popen:
        """在本机启动 ComfyUI 主进程（独立控制台窗口）。"""
        if not self.is_local:
            raise RuntimeError("远程实例无法在本机启动")
        if not self.valid_local():
            raise RuntimeError(f"目录中未找到 main.py: {self.root}")
        cmd = [python_exe, "main.py"]
        if args.strip():
            cmd += args.strip().split()
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        return subprocess.Popen(
            cmd, cwd=str(self.root), creationflags=creationflags,
            stdin=subprocess.DEVNULL,
        )
