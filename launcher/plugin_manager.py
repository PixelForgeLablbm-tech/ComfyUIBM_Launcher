# -*- coding: utf-8 -*-
"""插件（自定义节点）管理：扫描 / 克隆 / 更新 / 禁用 / 依赖。"""
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import git_utils
from .git_utils import NO_WINDOW
from .mirrors import git_extra_and_env, pip_env, pip_index_args


@dataclass
class PluginInfo:
    name: str
    path: str
    is_git: bool = False
    remote: str = ""
    branch: str = ""
    commit: str = ""
    dirty: bool = False
    has_requirements: bool = False
    disabled: bool = False
    behind: int = 0
    has_update: bool = False
    error: str = ""

    @property
    def status_text(self) -> str:
        parts = []
        if self.error:
            return f"错误: {self.error}"
        if self.disabled:
            parts.append("已禁用")
        elif self.is_git:
            parts.append("已启用")
        else:
            parts.append("本地文件夹")
        if self.dirty:
            parts.append("有本地改动")
        if self.has_requirements:
            parts.append("有依赖")
        return " · ".join(parts)


def custom_nodes_dir(instance_path) -> Path:
    return Path(instance_path) / "custom_nodes"


# git 信息 30s 缓存，避免每次进页面都跑一遍 git
_GIT_CACHE = {}
_GIT_CACHE_TTL = 30.0


def _git_info(dir_path: Path):
    info = (
        git_utils.remote_url(str(dir_path)) or "",
        git_utils.current_branch(str(dir_path)) or "",
        git_utils.short_commit(str(dir_path)) or "",
        git_utils.is_dirty(str(dir_path)),
    )
    return info


def _git_info_cached(dir_path: Path):
    key = str(dir_path)
    now = time.time()
    if key in _GIT_CACHE and now - _GIT_CACHE[key][0] < _GIT_CACHE_TTL:
        return _GIT_CACHE[key][1]
    info = _git_info(dir_path)
    _GIT_CACHE[key] = (now, info)
    return info


def has_requirements_file(dir_path: Path) -> bool:
    return (dir_path / "requirements.txt").exists() or \
        (dir_path / "install.py").exists()


# ---------- 扫描 ----------
def scan_plugins(instance_path: str) -> list:
    """扫描 custom_nodes 下的插件目录（不做网络操作）。

    git 信息查询（每个插件 4 条 git 命令）多线程并行，加快刷新。
    """
    base = custom_nodes_dir(instance_path)
    if not base.is_dir():
        return []
    try:
        entries = [e for e in base.iterdir() if e.is_dir()]
    except OSError:
        return []

    def build(entry) -> PluginInfo:
        raw = entry.name
        if not raw or raw.startswith("."):
            return None
        disabled = raw.endswith(".disabled")
        name = raw[:-len(".disabled")] if disabled else raw
        if not name:
            return None
        info = PluginInfo(name=name, path=str(entry), disabled=disabled,
                          has_requirements=has_requirements_file(entry))
        try:
            if git_utils.has_own_git_dir(entry):
                info.is_git = True
                repo, branch, commit, dirty = _git_info_cached(entry)
                info.remote = repo
                info.branch = branch
                info.commit = commit
                info.dirty = dirty
        except Exception as e:
            info.error = str(e)
        return info

    workers = min(8, max(1, len(entries)))
    plugins = []
    if len(entries) == 1:
        p = build(entries[0])
        if p:
            plugins.append(p)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for p in ex.map(build, entries):
                if p:
                    plugins.append(p)
    plugins.sort(key=lambda p: p.name.lower())
    return plugins


def check_plugin_updates(plugins: list, progress=None) -> list:
    """对 git 插件 fetch 并统计落后提交数（网络操作，需在后台线程）。"""
    result = []
    for p in plugins:
        if progress:
            progress(f"检查 {p.name} …")
        if not p.is_git or p.disabled:
            result.append(p)
            continue
        try:
            git_utils.run_git(p.path, "fetch", "origin", timeout=300)
            remote = git_utils.default_remote_branch(p.path)
            if remote:
                behind = git_utils.count_commits(p.path, f"HEAD..{remote}")
                p.behind = behind or 0
                p.has_update = behind is not None and behind > 0
        except Exception as e:
            p.error = str(e)
        result.append(p)
    return result


# ---------- 安装 ----------
def _clone_target(base: Path, url: str, name: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    if not name:
        name = (url.rstrip("/").split("/")[-1] or "plugin").replace(".git", "")
    target = base / name
    if target.exists():
        raise RuntimeError(f"目标目录已存在: {target}")
    return target


def clone_plugin(instance_path: str, url: str, name: str = "",
                 branch: str = "", shallow: bool = True,
                 mirrors: dict = None, progress=None) -> PluginInfo:
    """从 git 克隆插件到 custom_nodes/<name>。"""
    if progress:
        progress(f"正在克隆 {name or url} …")
    target = _clone_target(custom_nodes_dir(instance_path), url, name)
    extra, env = git_extra_and_env(mirrors or {})
    args = ["clone"]
    if shallow:
        args.append("--depth")
        args.append("1")
    if branch:
        args += ["--branch", branch]
    args += [url, str(target)]
    git_utils.run_git(instance_path, *args, timeout=1200, env=env,
                      extra_args=extra)
    info = PluginInfo(name=target.name, path=str(target), is_git=True,
                      remote=url, branch=branch or "",
                      has_requirements=has_requirements_file(target))
    return info


def copy_plugin_folder(instance_path: str, src: str, name: str = "",
                       progress=None) -> PluginInfo:
    """从本地文件夹复制一个插件到 custom_nodes。"""
    src_path = Path(src)
    if not src_path.is_dir():
        raise RuntimeError("源文件夹不存在")
    name = name or src_path.name
    target = custom_nodes_dir(instance_path) / name
    if target.exists():
        raise RuntimeError(f"目标目录已存在: {target}")
    if progress:
        progress(f"正在复制 {name} …")
    shutil.copytree(src_path, target)
    info = PluginInfo(name=name, path=str(target),
                      has_requirements=has_requirements_file(target))
    if git_utils.has_own_git_dir(target):
        info.is_git = True
        info.remote = git_utils.remote_url(str(target)) or ""
        info.branch = git_utils.current_branch(str(target)) or ""
        info.commit = git_utils.short_commit(str(target)) or ""
    return info


def install_requirements(plugin_path: str, python_exe: str,
                         mirrors: dict = None, progress=None) -> str:
    """安装插件依赖：requirements.txt 或 install.py。"""
    d = Path(plugin_path)
    env = dict(os.environ)
    env.update(pip_env(mirrors or {}))
    req = d / "requirements.txt"
    if req.exists():
        if progress:
            progress("正在安装 requirements.txt 依赖…")
        args = ["-m", "pip", "install"] + pip_index_args(mirrors or {}) + \
               ["-r", str(req)]
        proc = subprocess.run([python_exe] + args, cwd=str(d), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=3600, creationflags=NO_WINDOW,
                              stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
            raise RuntimeError(f"依赖安装失败 (exit {proc.returncode})\n{tail}")
        return "requirements 依赖安装完成"
    install_py = d / "install.py"
    if install_py.exists():
        if progress:
            progress("正在运行 install.py …")
        proc = subprocess.run([python_exe, "install.py", "--skip_requirements"],
                              cwd=str(d), env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=3600, creationflags=NO_WINDOW,
                              stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            tail = "\n".join((proc.stderr or "").strip().splitlines()[-15:])
            raise RuntimeError(f"install.py 执行失败 (exit {proc.returncode})\n{tail}")
        return "install.py 执行完成"
    raise RuntimeError("没有找到 requirements.txt 或 install.py")


# ---------- 更新 / 禁用 / 删除 ----------
def update_plugin(plugin: PluginInfo, mirrors: dict = None,
                  progress=None, python_exe: str = "python") -> PluginInfo:
    """更新插件：本地有改动时先 stash 保护；更新后自动安装依赖。"""
    if not plugin.is_git:
        raise RuntimeError("非 Git 插件，无法更新")
    if progress:
        progress(f"正在更新 {plugin.name} …")
    extra, env = git_extra_and_env(mirrors or {})
    stashed = git_utils.is_dirty(plugin.path)
    if stashed:
        git_utils.run_git(plugin.path, "stash", check=False)
    try:
        git_utils.fast_forward_pull(plugin.path, env=env, extra_args=extra)
    finally:
        if stashed:
            git_utils.stash(plugin.path, pop=True)
    plugin.commit = git_utils.short_commit(plugin.path) or ""
    plugin.behind = 0
    plugin.has_update = False
    plugin.error = ""
    plugin.dirty = git_utils.is_dirty(plugin.path)
    # 更新后自动安装依赖（有 requirements.txt / install.py 时）
    if plugin.has_requirements:
        if progress:
            progress(f"正在为 {plugin.name} 安装依赖…")
        try:
            install_requirements(plugin.path, python_exe,
                                 mirrors=mirrors, progress=progress)
        except Exception as e:
            # 代码已更新成功，依赖失败仅提示，不阻塞
            if progress:
                progress(f"⚠ {plugin.name} 依赖安装失败：{e}\n"
                         "（代码已更新，可稍后重试依赖安装）")
    return plugin


def toggle_plugin(plugin: PluginInfo) -> None:
    """禁用/启用：通过重命名为 xxx.disabled 实现。"""
    src = Path(plugin.path)
    if plugin.disabled:
        name = src.name
        if name.endswith(".disabled"):
            name = name[: -len(".disabled")]
        dst = src.with_name(name)
        src.rename(dst)
        plugin.path = str(dst)
        plugin.disabled = False
    else:
        dst = src.with_name(src.name + ".disabled")
        src.rename(dst)
        plugin.path = str(dst)
        plugin.disabled = True


def remove_plugin(plugin: PluginInfo) -> None:
    shutil.rmtree(plugin.path, ignore_errors=True)
