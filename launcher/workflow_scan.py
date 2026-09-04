# -*- coding: utf-8 -*-
"""工作流识别：解析 ComfyUI 工作流 → 用到的自定义节点 → 匹配已安装/未安装插件。

设计：只做识别与分类，不做自动安装——未安装插件给出插件名（仓库名），
用户复制后在「插件管理 → 插件搜索」里搜索安装。

节点→插件映射数据来自 ComfyUI-Manager 官方维护的 extension-node-map.json
（assets/extension-node-map.json，随程序打包）。
"""
import ast
import json
import sys
from pathlib import Path

_INDEX_CACHE = None        # {"node2repo": {}, "repo2nodes": {}}
_INSTALLED_CACHE = {}      # instance_path -> {节点: folder}（30s 失效）


def node_map_path():
    base = Path(getattr(sys, "_MEIPASS",
                        Path(__file__).resolve().parent.parent))
    return base / "assets" / "extension-node-map.json"


def _indexes():
    """加载节点映射，返回 {"node2repo", "repo2nodes"}（惰性 + 缓存）。"""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        node2repo, repo2nodes = {}, {}
        p = node_map_path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for repo, val in data.items():
                    nodes = val[0] if isinstance(val, list) and val else []
                    if isinstance(val, dict):
                        nodes = []
                    if nodes:
                        repo2nodes.setdefault(repo, set()).update(nodes)
                        for n in nodes:
                            node2repo.setdefault(n, repo)
            except Exception:
                pass
        _INDEX_CACHE = {"node2repo": node2repo, "repo2nodes": repo2nodes}
    return _INDEX_CACHE


def repo_short_name(repo: str) -> str:
    """仓库 URL → 插件名（最后一段，去 .git）。"""
    return (repo.rstrip("/").split("/")[-1] or repo).replace(".git", "")


# ComfyUI 主仓库：映射表里登记了它的内置节点，识别时应视为"内置"而非可装插件
_CORE_REPOS = {
    "https://github.com/comfyanonymous/ComfyUI",
    "github.com/comfyanonymous/ComfyUI",
}


def _is_core_repo(repo: str) -> bool:
    r = (repo or "").replace(".git", "")
    return r in _CORE_REPOS


def parse_workflow(path) -> list:
    """解析工作流文件 → 去重的节点类型列表（保持出现顺序）。

    兼容 ComfyUI 三种常见格式：
      - UI 格式：{"nodes": [{"type": "KSampler"}, ...]}
      - API 格式：{"3": {"class_type": "KSampler"}, ...}
      - 导出带 workflow：{"prompt": {...}, "workflow": {"nodes": [...]}}
    """
    try:
        data = json.loads(Path(path).read_text(
            encoding="utf-8-sig", errors="replace"))
    except Exception as e:
        raise RuntimeError(f"无法解析工作流 JSON：{e}")

    seen, out = set(), []

    def add(n):
        if isinstance(n, str) and n and n not in seen:
            seen.add(n)
            out.append(n)

    if isinstance(data, dict):
        # UI 格式顶层
        if isinstance(data.get("nodes"), list):
            for nd in data["nodes"]:
                if isinstance(nd, dict):
                    add(nd.get("type"))
        # API 格式（顶层按 id 的 class_type）
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("class_type"), str):
                add(v.get("class_type"))
        # 导出文件里嵌套的 UI 格式 workflow
        wf = data.get("workflow")
        if isinstance(wf, dict) and isinstance(wf.get("nodes"), list):
            for nd in wf["nodes"]:
                if isinstance(nd, dict):
                    add(nd.get("type"))
    if not out:
        raise RuntimeError("工作流中没有识别到节点")
    return out


# ---------------------------------------------------------------- 已安装节点扫描
def _extract_node_names(folder: Path) -> set:
    """静态扫描插件目录里 NODE_CLASS_MAPPINGS / EXTENSION_NODE_MAPPINGS 的键。"""
    names = set()
    for py in folder.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id in (
                        "NODE_CLASS_MAPPINGS", "EXTENSION_NODE_MAPPINGS"):
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) \
                                    and isinstance(k.value, str):
                                names.add(k.value)
    return names


def scan_installed_plugins(instance_path: str):
    """扫描实例 custom_nodes 里已安装插件能提供的节点。

    返回 {插件文件夹名: {"remote": str, "nodes": [节点...]}}。
    """
    import time
    from . import git_utils
    from .plugin_manager import custom_nodes_dir

    global _INSTALLED_CACHE
    now = time.time()
    cached = _INSTALLED_CACHE.get(instance_path)
    if cached and now - cached[0] < 30:
        return cached[1]

    base = custom_nodes_dir(instance_path)
    repo2nodes = _indexes()["repo2nodes"]
    result = {}
    if base.is_dir():
        for folder in base.iterdir():
            if not folder.is_dir() or folder.name.startswith(".") \
                    or folder.name == "__pycache__":
                continue
            remote = ""
            try:
                remote = git_utils.remote_url(str(folder)) or ""
            except Exception:
                pass
            nodes = set(_extract_node_names(folder))
            if remote and remote in repo2nodes:
                nodes |= set(repo2nodes[remote])
            result[folder.name] = {"remote": remote,
                                   "nodes": sorted(nodes)}
    _INSTALLED_CACHE[instance_path] = (now, result)
    return result


# ---------------------------------------------------------------- 分析
def analyze_workflow(instance_path: str, wf_path):
    """分析工作流，返回插件级分类（多个节点归到同一个插件）。

    返回 {
      "installed": [{"name": 插件文件夹, "nodes": [...]}],
      "missing":   [{"name": 插件名, "repo": 仓库URL, "nodes": [...]}],
      "unmapped":  [节点名...],   # 不在映射表、本地也扫不到 → 可能是内置节点
    }
    """
    nodes = parse_workflow(wf_path)
    node2repo = _indexes()["node2repo"]
    installed = scan_installed_plugins(instance_path)

    # 已安装插件能提供的节点（文件夹名 + 扫描到的节点名）
    inst_nodes = {}
    inst_by_name = {}
    for fname, info in installed.items():
        for n in info["nodes"]:
            inst_nodes.setdefault(n, fname)
        inst_by_name[fname.lower()] = fname

    inst_result = {}     # fname -> nodes
    miss_result = {}     # repo -> nodes
    unmapped = []
    for n in nodes:
        if n in inst_nodes:
            inst_result.setdefault(inst_nodes[n], []).append(n)
            continue
        repo = node2repo.get(n)
        if not repo or _is_core_repo(repo):
            unmapped.append(n)      # 内置节点（映射表里登记在主仓库下）
            continue
        pname = repo_short_name(repo)
        # 插件是否已安装：目录名匹配 或 本地某插件 remote 匹配该仓库
        installed_fname = inst_by_name.get(pname.lower())
        if installed_fname:
            inst_result.setdefault(installed_fname, []).append(n)
        else:
            miss_result.setdefault(repo, {"name": pname,
                                          "repo": repo,
                                          "nodes": []})["nodes"].append(n)
    return {
        "installed": [{"name": k, "nodes": v}
                      for k, v in sorted(inst_result.items())],
        "missing": list(miss_result.values()),
        "unmapped": unmapped,
    }
