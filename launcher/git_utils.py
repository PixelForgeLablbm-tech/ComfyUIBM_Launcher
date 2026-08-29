# -*- coding: utf-8 -*-
"""git 子进程封装（所有 git 操作统一走这里）。"""
import os
import subprocess
from typing import Optional

# Windows 下不弹出黑色控制台窗口
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class GitError(RuntimeError):
    pass


def _norm_git_path(p) -> str:
    """统一为 git 偏好的正斜杠形式（safe.directory 匹配更稳）。"""
    return str(p).replace("\\", "/")


def run_git(cwd, *args, timeout=180, check=True, env=None, extra_args=None):
    """在 cwd 目录执行 git 命令，返回 CompletedProcess。

    自动注入 -c safe.directory=<cwd>：免去拷贝安装 / 移动盘等场景的
    "dubious ownership" 报错（仅本次命令生效，不修改全局配置）。
    extra_args: 插在子命令前的参数（用于注入 -c 加速配置）；
    env: 额外环境变量（如代理），自动合并到当前环境。
    """
    trust = []
    if cwd:
        trust = ["-c", f"safe.directory={_norm_git_path(cwd)}"]
    cmd = ["git"] + trust + list(extra_args or []) + list(args)
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=NO_WINDOW,
            stdin=subprocess.DEVNULL,
            env=full_env,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git 命令超时: git {' '.join(args)}")
    except FileNotFoundError:
        raise GitError("未找到 git，请先安装并加入 PATH")
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise GitError(err or f"git {' '.join(args)} 失败 (exit {proc.returncode})")
    return proc


def is_git_repo(path) -> bool:
    try:
        p = run_git(path, "rev-parse", "--is-inside-work-tree", check=False)
        return p.returncode == 0 and p.stdout.strip() == "true"
    except Exception:
        return False


def has_own_git_dir(path) -> bool:
    """目录是否自带 .git（独立 git 仓库 / 子模块），用于插件识别。

    注意：is_git_repo 对嵌套在主仓库工作树内的目录也会返回 True，
    插件扫描必须用本函数区分「独立仓库」与「普通子目录」。
    """
    from pathlib import Path
    return (Path(path) / ".git").exists()


def current_branch(path) -> Optional[str]:
    try:
        b = run_git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        return None if b == "HEAD" else b
    except Exception:
        return None


def short_commit(path) -> Optional[str]:
    try:
        return run_git(path, "rev-parse", "--short", "HEAD").stdout.strip()
    except Exception:
        return None


def remote_url(path) -> Optional[str]:
    try:
        return run_git(path, "remote", "get-url", "origin").stdout.strip() or None
    except Exception:
        return None


def describe(path, abbrev=0) -> str:
    """git describe：--abbrev=0 只返回标签名。"""
    try:
        return run_git(path, "describe", "--tags", "--abbrev=0").stdout.strip()
    except Exception:
        return ""


def describe_full(path) -> str:
    """git describe --tags --always：标签优先，其次短提交。"""
    try:
        return run_git(path, "describe", "--tags", "--always").stdout.strip()
    except Exception:
        return ""


def default_remote_branch(path) -> Optional[str]:
    """返回 origin 的默认远程分支（如 origin/main），失败返回 None。"""
    try:
        p = run_git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD",
                    check=False)
        if p.returncode == 0:
            return p.stdout.strip()
    except Exception:
        pass
    for branch in ("main", "master"):
        try:
            run_git(path, "rev-parse", "--verify", f"origin/{branch}")
            return f"origin/{branch}"
        except Exception:
            continue
    return None


def count_commits(path, range_spec) -> Optional[int]:
    try:
        p = run_git(path, "rev-list", "--count", range_spec)
        return int(p.stdout.strip())
    except Exception:
        return None


def changelog(path, range_spec, limit=100) -> str:
    try:
        p = run_git(path, "log", "--oneline", "--no-merges",
                    f"-{limit}", range_spec)
        return p.stdout.strip()
    except Exception:
        return ""


def rev_parse_short(path, ref) -> Optional[str]:
    try:
        return run_git(path, "rev-parse", "--short", ref).stdout.strip()
    except Exception:
        return None


def rev_parse_full(path, ref) -> Optional[str]:
    try:
        return run_git(path, "rev-parse", ref).stdout.strip()
    except Exception:
        return None


def is_dirty(path) -> bool:
    """工作区是否有未提交改动。"""
    try:
        p = run_git(path, "status", "--porcelain")
        return bool(p.stdout.strip())
    except Exception:
        return False


def stash(path, pop=False):
    """暂存 / 恢复本地改动（不抛错时静默）。"""
    try:
        run_git(path, "stash" if not pop else "stash", "pop", check=False)
    except Exception:
        pass


def fast_forward_pull(path, env=None, extra_args=None) -> None:
    """fetch + 快进合并，不依赖 upstream 跟踪配置（比 git pull 更稳健）。

    若远程分支存在冲突（非快进）会抛出 GitError。
    """
    run_git(path, "fetch", "origin", timeout=600, env=env,
            extra_args=extra_args)
    remote = default_remote_branch(path)
    if not remote:
        raise GitError("无法确定远程分支，无法更新")
    run_git(path, "merge", "--ff-only", remote, timeout=600, env=env,
            extra_args=extra_args)
