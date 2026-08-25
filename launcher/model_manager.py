# -*- coding: utf-8 -*-
"""模型（模组）管理：分类扫描 / 统计 / 导入（同名自动改名）。

分类不预设：直接读取 models/ 下真实存在的文件夹作为分类列表。
"""
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# 常见可导入的文件扩展名（用于文件对话框过滤）
MODEL_EXTS = ("*.safetensors *.ckpt *.pt *.pth *.bin *.onnx *.gguf *.sft "
              "*.pkl *.safetensors.*")

# 单分类最多返回的条目数（超出取体积最大的 N 个）
CATEGORY_ITEM_CAP = 5000


@dataclass
class ModelFile:
    path: str
    name: str
    size: int
    mtime: float
    ext: str


def models_dir(instance_path) -> Path:
    return Path(instance_path) / "models"


def category_summary(instance_path: str) -> list:
    """直接读取 models/ 下的文件夹作为分类列表（不使用预设名）。

    每个子目录（隐藏目录除外）即一个分类，显示名用目录原始名；
    标签形如「checkpoints · 12 · 3.45 GB」；按目录名排序。
    多个分类目录并行扫描，加快刷新速度。
    """
    base = models_dir(instance_path)
    dirs = []
    if base.is_dir():
        try:
            dirs = [d for d in base.iterdir()
                    if d.is_dir() and not d.name.startswith(".")]
        except OSError:
            dirs = []
    if not dirs:
        return []
    workers = min(8, max(1, len(dirs)))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_scan_one, d): d for d in dirs}
        for fut, d in futures.items():
            items = fut.result()
            total = sum(i.size for i in items)
            if items:
                suffix = (f"（显示前 {CATEGORY_ITEM_CAP} 个）"
                          if len(items) >= CATEGORY_ITEM_CAP else "")
                label = f"{d.name} · {len(items)} · {human_size(total)}{suffix}"
            else:
                label = d.name
            results.append({"category": d.name, "label": label,
                            "path": str(d), "count": len(items),
                            "total": total, "items": items})
    results.sort(key=lambda r: r["category"].lower())
    return results


def scan_category_dir(d: Path) -> list:
    """递归扫描分类目录（os.scandir 迭代，比 rglob 快）。"""
    files = []
    stack = [d]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(Path(e.path))
                    else:
                        try:
                            st = e.stat()
                        except OSError:
                            continue
                        files.append(ModelFile(
                            path=e.path, name=e.name, size=st.st_size,
                            mtime=st.st_mtime,
                            ext=Path(e.name).suffix.lower(),
                        ))
        except OSError:
            continue
    return files


def _scan_one(d: Path) -> list:
    """供线程池使用的单分类扫描（返回按大小降序的文件）。"""
    items = scan_category_dir(d)
    items.sort(key=lambda f: f.size, reverse=True)
    if len(items) > CATEGORY_ITEM_CAP:
        items = items[:CATEGORY_ITEM_CAP]
    return items


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    value = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024.0 or unit == "TB":
            return f"{value:.2f} {unit}"
    return f"{value:.2f} TB"


def import_models(src_paths, dst_dir, progress=None, cancel=None):
    """复制模型到分类目录；同名自动加后缀 _1 _2（不覆盖原文件）。

    返回 (成功数, 跳过数, 目标文件名列表)。
    """
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    ok = skipped = 0
    copied = []
    total = len(src_paths)
    for i, sp in enumerate(src_paths):
        if cancel and cancel():
            break
        src = Path(sp)
        if not src.is_file():
            skipped += 1
            continue
        stem = src.stem
        ext = src.suffix
        final = dst / src.name
        n = 1
        while final.exists():
            final = dst / f"{stem}_{n}{ext}"
            n += 1
        if progress:
            progress(f"({i + 1}/{total}) 复制: {src.name}")
        try:
            shutil.copy2(str(src), str(final))
        except OSError:
            skipped += 1
            continue
        ok += 1
        copied.append(final.name)
    return ok, skipped, copied
