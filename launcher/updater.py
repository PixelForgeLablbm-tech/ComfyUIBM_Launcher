# -*- coding: utf-8 -*-
"""ComfyUI 本体版本更新：版本列表、更新/回滚、依赖智能安装。"""
import os
import re
import subprocess
import time
from pathlib import Path

from . import git_utils
from .git_utils import NO_WINDOW
from .mirrors import git_extra_and_env, pip_env, pip_index_args

STABLE_TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


# ---------------------------------------------------------------- 当前版本
def version(comfyui_path: str) -> str:
    """当前版本描述：标签 (提交)。"""
    d = Path(comfyui_path)
    if not d.joinpath(".git").exists():
        return "非 git 安装"
    tag = git_utils.describe(d)
    commit = git_utils.short_commit(d) or ""
    if tag and commit:
        return f"{tag} ({commit})"
    if tag:
        return tag
    return "git 安装"


# ---------------------------------------------------------------- 版本列表
_VERSION_CACHE = {"key": None, "at": 0.0, "info": None}
_VERSION_CACHE_TTL = 60.0


def _parse_version(name: str):
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", name.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def list_versions(inst, mirrors: dict, progress=None):
    """拉取远端版本列表：发布版 tags + 主干分支。60s 缓存。"""
    d = Path(inst.path)
    if not d.joinpath(".git").exists():
        raise RuntimeError("该实例不是 git 安装，无法获取版本列表")
    remote = git_utils.remote_url(str(d)) or ""
    cache_key = f"{inst.path.lower()}|{remote}"
    if _VERSION_CACHE["key"] == cache_key and \
            time.time() - _VERSION_CACHE["at"] < _VERSION_CACHE_TTL:
        return _VERSION_CACHE["info"]

    extra, env = git_extra_and_env(mirrors)
    if progress:
        progress("正在查询远端版本列表…")
    # 一次 ls-remote 同时拿 tags + heads（减少网络往返）
    ls = None
    if remote:
        ls = git_utils.run_git(str(d), "ls-remote", "--tags", "--heads",
                               remote, timeout=120, check=False, env=env,
                               extra_args=extra)

    current_commit = git_utils.rev_parse_full(str(d), "HEAD") or ""

    # 解析 tags 与 heads（同名 tag 行优先保留 ^{} 的最终 commit）
    tag_map = {}
    branch_raw = []
    if ls and ls.returncode == 0:
        for line in ls.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            commit, ref = parts[0], parts[1]
            if ref.startswith("refs/tags/"):
                name = ref.removeprefix("refs/tags/")
                peeled = name.endswith("^{}")
                name = name.removesuffix("^{}")
                if name in tag_map:
                    if peeled:
                        tag_map[name] = commit
                else:
                    tag_map[name] = commit
            elif ref.startswith("refs/heads/"):
                name = ref.removeprefix("refs/heads/")
                if name in ("master", "main"):
                    branch_raw.append((name, commit))

    tags = []
    for name, commit in tag_map.items():
        if not STABLE_TAG_RE.match(name):
            continue
        tags.append({
            "name": name,
            "commit": commit[:12],
            "date": None,
            "is_current": bool(current_commit) and (
                commit.startswith(current_commit) or
                current_commit.startswith(commit)),
        })
    tags.sort(key=lambda t: _parse_version(t["name"]) or (0, 0, 0),
              reverse=True)

    # 拉取 tag 对象（blobless 优先，失败降级），随后一条命令拿全部发布日期
    if tags:
        fetch_ok = git_utils.run_git(
            str(d), "fetch", "origin", "--tags", "--prune",
            "--filter=blob:none", "--quiet", timeout=600, check=False,
            env=env, extra_args=extra).returncode == 0
        if not fetch_ok:
            fetch_ok = git_utils.run_git(
                str(d), "fetch", "origin", "--tags", "--prune", "--quiet",
                timeout=600, check=False, env=env,
                extra_args=extra).returncode == 0
        if fetch_ok:
            # 一条 for-each-ref 拿到所有 tag 的发布日期（替代逐 tag 跑 git log）
            dates = {}
            p = git_utils.run_git(
                str(d), "for-each-ref",
                "--format=%(refname:short) %(creatordate:short)",
                "refs/tags", check=False, env=env, extra_args=extra)
            if p.returncode == 0:
                for line in p.stdout.splitlines():
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        dates[parts[0]] = parts[1]
            for t in tags:
                t["date"] = dates.get(t["name"])

    # 主干分支
    branches = []
    for name, commit in branch_raw:
        branches.append({
            "name": name,
            "commit": commit[:12],
            "date": None,
            "is_current": bool(current_commit) and (
                commit.startswith(current_commit) or
                current_commit.startswith(commit)),
        })

    info = {
        "current": version(inst.path),
        "git_install": True,
        "latest_tag": tags[0]["name"] if tags else None,
        "latest_commit": tags[0]["commit"] if tags else None,
        "tags": tags,
        "branches": branches,
    }
    _VERSION_CACHE.update(key=cache_key, at=time.time(), info=info)
    return info


# ---------------------------------------------------------------- 更新操作
def _dirty_stash(path, mirrors=None):
    """本地有改动时先暂存，返回是否暂存过。"""
    if git_utils.is_dirty(path):
        git_utils.run_git(path, "stash", check=False)
        return True
    return False


def update_to(inst, target: str, mirrors: dict, progress=None):
    """更新/回滚到指定版本（tag 或分支）。自动对比依赖并安装。"""
    d = Path(inst.path)
    if not d.joinpath(".git").exists():
        raise RuntimeError("该实例不是 git 安装，无法更新")
    if not target.strip():
        raise RuntimeError("请先选择一个版本")
    extra, env = git_extra_and_env(mirrors)
    if progress:
        progress(f"正在拉取远端数据…（目标：{target}）")
    # 完整拉取优先（需要 blob 对比依赖），失败降级轻量拉取
    fetched = git_utils.run_git(str(d), "fetch", "origin", "--tags", "--prune",
                                timeout=600, check=False, env=env,
                                extra_args=extra).returncode == 0
    if not fetched:
        if progress:
            progress("完整拉取不顺利，改用轻量拉取…")
        fetched = git_utils.run_git(
            str(d), "fetch", "origin", "--tags", "--prune",
            "--filter=blob:none", timeout=600, check=False, env=env,
            extra_args=extra).returncode == 0
        if not fetched:
            raise RuntimeError("拉取远端数据失败，请检查网络、代理或 GitHub 加速设置")

    # 更新前的 requirements 快照
    old_req = None
    p = git_utils.run_git(str(d), "show", "HEAD:requirements.txt", check=False)
    if p.returncode == 0:
        old_req = p.stdout

    stashed = _dirty_stash(str(d))
    if progress:
        progress(f"正在切换 {target} …")
    git_utils.run_git(str(d), "checkout", target, check=False, env=env,
                      extra_args=extra)
    r = git_utils.run_git(str(d), "reset", "--hard", target, check=False,
                          env=env, extra_args=extra)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"切换 {target} 失败")
    if stashed:
        git_utils.stash(str(d), pop=True)

    # 对比目标版本与更新前版本的 requirements.txt
    new_req = None
    p2 = git_utils.run_git(str(d), "show", f"{target}:requirements.txt",
                           check=False)
    if p2.returncode == 0:
        new_req = p2.stdout
    deps_changed = True
    if old_req is not None and new_req is not None:
        deps_changed = old_req.strip() != new_req.strip()

    if not deps_changed:
        if progress:
            progress(f"更新完成：已切换至 {target}（依赖无变化，已跳过安装）")
        return f"已切换至 {target}（依赖无变化）"
    if progress:
        progress(f"已切换至 {target}，检测到依赖变化，自动安装…")
    try:
        install_requirements(inst, mirrors, progress)
        if progress:
            progress(f"更新完成：已切换至 {target}，依赖安装完毕")
        return f"已切换至 {target}，依赖安装完毕"
    except Exception as e:
        raise RuntimeError(
            f"版本已切换至 {target}，但依赖安装失败：{e}\n"
            "如果启动 ComfyUI 报错，请点「安装 requirements」重试，"
            "或回到版本列表回滚。") from e


def update_comfyui(inst, mirrors: dict, progress=None):
    """更新 ComfyUI 本体：拉取最新分支 + 安装依赖。"""
    d = Path(inst.path)
    if not d.joinpath(".git").exists():
        raise RuntimeError("该实例不是 git 安装，无法在线更新")
    extra, env = git_extra_and_env(mirrors)
    if progress:
        progress("正在拉取 ComfyUI 最新代码…")
    git_utils.run_git(str(d), "fetch", "origin", "--tags", "--prune",
                      timeout=600, env=env, extra_args=extra)
    stashed = _dirty_stash(str(d))
    git_utils.fast_forward_pull(str(d), env=env, extra_args=extra)
    if stashed:
        git_utils.stash(str(d), pop=True)
    install_requirements(inst, mirrors, progress)
    if progress:
        progress("更新完成（已安装依赖）")


def install_requirements(inst, mirrors: dict, progress=None):
    """安装 ComfyUI requirements.txt（带 PyPI 镜像 / 代理 / HF 镜像环境）。"""
    req = Path(inst.path) / "requirements.txt"
    if not req.exists():
        raise RuntimeError("未找到 requirements.txt")
    if progress:
        progress("正在安装依赖（可能需要几分钟）…")
    python = inst.resolve_python("python")
    env = dict(os.environ)
    env.update(pip_env(mirrors))
    args = ["-m", "pip", "install"] + pip_index_args(mirrors) + \
           ["-r", str(req)]
    proc = subprocess.run([python] + args, cwd=inst.path, env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=3600,
                          creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"依赖安装失败 (exit {proc.returncode})\n{tail}")
    if progress:
        progress("依赖安装完成")


# ---------------------------------------------------------------- 兼容旧接口
class UpdateInfo:
    """一次更新检查的结果（check_update 使用）。"""

    def __init__(self):
        self.ok = False
        self.is_git = False
        self.current = ""
        self.latest = ""
        self.branch = ""
        self.behind = 0
        self.has_update = False
        self.changelog = ""
        self.error = ""

    @property
    def status_text(self) -> str:
        if self.error:
            return self.error
        if not self.is_git:
            return "非 Git 安装"
        if self.has_update:
            return f"可更新 (+{self.behind})"
        return "已是最新"


def check_update(path: str, fetch: bool = True) -> UpdateInfo:
    """检查本地 ComfyUI 的更新（fetch 默认开启）。"""
    info = UpdateInfo()
    try:
        if not git_utils.is_git_repo(path):
            info.error = "非 Git 安装，无法自动更新"
            return info
        info.is_git = True
        info.branch = git_utils.current_branch(path) or ""
        info.current = git_utils.short_commit(path) or ""
        if fetch:
            git_utils.run_git(path, "fetch", "origin", timeout=600)
        remote = git_utils.default_remote_branch(path)
        if not remote:
            info.error = "无法确定远程分支"
            return info
        behind = git_utils.count_commits(path, f"HEAD..{remote}")
        info.behind = behind or 0
        info.has_update = behind is not None and behind > 0
        info.latest = git_utils.rev_parse_short(path, remote) or info.current
        info.changelog = git_utils.changelog(path, f"HEAD..{remote}")
        info.ok = True
    except Exception as e:
        info.error = str(e)
    return info


def pull(path: str, install_deps: bool = False, python_exe: str = "python",
         progress=None):
    """拉取更新，返回 (ok, message)。"""
    def log(msg):
        if progress:
            progress(msg)

    try:
        log("正在拉取最新代码…")
        git_utils.fast_forward_pull(path)
        log("代码更新完成。")
        if install_deps:
            req = Path(path) / "requirements.txt"
            if req.exists():
                log("正在更新依赖 (pip install -r requirements.txt)…")
                subprocess.run(
                    [python_exe, "-m", "pip", "install", "-r", str(req)],
                    cwd=path, creationflags=NO_WINDOW, timeout=3600,
                    stdin=subprocess.DEVNULL,
                )
                log("依赖更新完成。")
        return True, "更新成功"
    except Exception as e:
        return False, str(e)
