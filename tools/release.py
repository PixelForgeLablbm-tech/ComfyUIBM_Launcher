# -*- coding: utf-8 -*-
"""一键发布到 GitHub Releases。

用法:
    python tools/release.py --token ghp_xxxxxxxx --tag v1.0.0 [--setup dist\\ComfyUIBM_Launcher_Setup.exe]

功能:
    1. 若仓库不存在则创建公开仓库 ComfyUIBM_Launcher
    2. 创建 Release（草稿，可先预览再 Publish）
    3. 上传 setup.exe 安装包

Token 获取: GitHub → Settings → Developer settings → Personal access tokens
→ Generate new token (classic) → 勾选 repo → 生成并复制
"""
import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests

USER = "PixelForgeLablbm-tech"
REPO = "ComfyUIBM_Launcher"
API = "https://api.github.com"

RELEASE_NOTES = """## ComfyUIBM启动器 v1.2.1

基于 Python + PyQt5 的 ComfyUI 本地管理工具。

### v1.2.1 更新内容（修复更新下载）
- **修复：更新文件下载走 GitHub 加速镜像**：直连 github.com 不通的网络
  （如部分国内网络）也能正常下载更新，失败自动重试镜像
- **修复：更新替换更稳健**：替换失败会写错误日志并保留旧版，
  成功时自动清理旧版 onedir 残留
- **受限网络用户提示**：若软件内更新下载失败，可在「设置 → 网络」开启
  代理后重试；或手动下载：
  https://github.com/PixelForgeLablbm-tech/ComfyUIBM_Launcher/releases

### v1.2.0 更新内容（内核维护全面升级）
- **事务式安装**：Torch / xformers / SageAttention / llama-cpp / Triton 全部改为
  预检（dry-run）→ 快照 → 安装（实时进度）→ 装后验证 → 失败自动回滚，
  安装失败不会破坏原有版本
- **Torch**：torchvision / torchaudio 按官方配套版本自动锁定；验证 CUDA 可用性
- **xformers / SageAttention / llama-cpp**：按已装 torch 版本 + CUDA 自动匹配
  官方 Windows 轮子（可弹窗手动改选），装后真实内核实测验证
- **Triton**：改用 triton-windows（Windows 可安装）
- **GitHub 加速**：wheel 下载 / 回滚下载自动走 gh-proxy，失败自动重试
- **修复**：
  - 损坏的 dist-info 导致 torch 版本识别为 None（回退 import 取真实版本）
  - wheel 文件名 %2B 未解码导致 "Invalid wheel filename"
  - 关闭窗口时后台任务线程崩溃（TaskSignals deleted）
  - SageAttention 版本表 cu128 假条目（2.11.0）
  - 关闭时有后台任务先提醒，避免中断安装

### 功能
- **启动控制台**：显存模式 / 端口 / GPU 设备选择 / 实时日志 / 就绪自动开浏览器
- **实例管理**：自动扫描本机 ComfyUI 安装，一键添加
- **模型管理**：直接读取 models 文件夹分类，搜索/排序/分页/导入
- **插件管理**：克隆安装 / 插件搜索（GitHub）/ 更新（自动装依赖）
- **更新维护**：ComfyUI 版本列表 / 更新回滚 / 依赖智能安装
- **内核维护**：Torch / xformers / Triton / llama-cpp / SageAttention 安装（事务式）
- **文件管理**：一键打开根目录 / 工作流 / 自定义节点 / 输入输出图片
- **网络加速**：PyPI 镜像 / HF 镜像 / 代理 / GitHub 加速
- **主题**：深色 / 浅色 / 跟随系统
- **安装卸载**：安装向导（选路径/快捷方式）+ 卸载器

### 使用说明
- 安装后如需更新功能，请确保本机已安装 git
"""


def _headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ComfyUIBM-Launcher",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True, help="GitHub Personal Access Token")
    ap.add_argument("--tag", default="v1.0.0")
    ap.add_argument("--setup", default="dist/ComfyUIBM_Launcher_Setup.exe")
    args = ap.parse_args()

    setup = Path(args.setup)
    if not setup.exists():
        print(f"错误：找不到安装包 {setup}，请先打包")
        sys.exit(1)

    headers = _headers(args.token)

    # 1. 检查 / 创建仓库
    r = requests.get(f"{API}/repos/{USER}/{REPO}", headers=headers, timeout=30)
    if r.status_code == 404:
        r = requests.post(f"{API}/user/repos", headers=headers, timeout=30,
                          json={"name": REPO,
                                "description": "ComfyUIBM启动器 —— ComfyUI 管理工具",
                                "private": False,
                                "auto_init": True})
        if r.status_code not in (200, 201):
            print(f"创建仓库失败: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        print("✔ 仓库已创建")
    elif r.status_code == 200:
        print("✔ 仓库已存在")
    else:
        print(f"查询仓库失败: {r.status_code} {r.text[:300]}")
        sys.exit(1)

    # 2. 创建 Release（直接发布，供「检查更新」检测）
    r = requests.post(f"{API}/repos/{USER}/{REPO}/releases", headers=headers,
                      timeout=30, json={
                          "tag_name": args.tag,
                          "name": args.tag,
                          "body": RELEASE_NOTES,
                          "draft": False,
                      })
    if r.status_code not in (200, 201):
        # tag 已存在时尝试更新同名 release
        if r.status_code == 422:
            r2 = requests.get(f"{API}/repos/{USER}/{REPO}/releases/tags/{args.tag}",
                              headers=headers, timeout=30)
            if r2.status_code == 200:
                rid = r2.json()["id"]
                r = requests.patch(f"{API}/repos/{USER}/{REPO}/releases/{rid}",
                                   headers=headers, timeout=30,
                                   json={"name": args.tag, "body": RELEASE_NOTES,
                                         "draft": False})
        if r.status_code not in (200, 201):
            print(f"创建 Release 失败: {r.status_code} {r.text[:300]}")
            sys.exit(1)
    release = r.json()
    print(f"✔ Release 已发布: {args.tag}")

    # 3. 上传 setup.exe
    upload_url = release["upload_url"].split("{")[0]
    with open(setup, "rb") as f:
        r = requests.post(
            f"{upload_url}?name={setup.name}",
            headers={**headers, "Content-Type": "application/octet-stream"},
            data=f, timeout=600)
    if r.status_code not in (200, 201):
        print(f"上传安装包失败: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    print(f"✔ 安装包已上传: {setup.name}")

    print("=" * 40)
    print(f"发布完成（草稿）！请到仓库页面检查并点 Publish release：")
    print(f"  https://github.com/{USER}/{REPO}/releases")
    print("发布后，用户打开启动器 → 设置 → 检查更新 即可发现新版本。")


if __name__ == "__main__":
    main()
