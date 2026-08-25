# -*- coding: utf-8 -*-
"""克隆安装逻辑验证：用本地 git 仓库模拟远端，走完整 clone_plugin 链路。"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / ".clone_tmp"
if TMP.exists():
    shutil.rmtree(TMP)              # 幂等：每次全新运行（失败会抛，不吞）
TMP.mkdir(exist_ok=True)
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def sh(cwd, *args):
    cmd = ["git", *[str(a).replace("\\", "/") for a in args]]
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    from launcher import plugin_manager
    from launcher.instance import Instance
    from launcher.config import Config

    # 1. 构造"远端"插件仓库（含 requirements.txt）
    repo = TMP / "MyPlugin"
    repo.mkdir(exist_ok=True)
    (repo / "__init__.py").write_text("print('plugin')\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("requests\n", encoding="utf-8")
    sh(repo, "init")
    sh(repo, "config", "user.email", "t@t")
    sh(repo, "config", "user.name", "t")
    sh(repo, "add", ".")
    sh(repo, "commit", "-m", "init")

    # 2. 假实例（fake_comfy/custom_nodes）
    fake = TMP / "fake_comfy"
    fake.mkdir(parents=True, exist_ok=True)
    (fake / "main.py").write_text("print('x')\n", encoding="utf-8")
    (fake / "comfy").mkdir(exist_ok=True)
    inst = Instance(name="fake", type="local", path=str(fake))

    # 3. 用 file:// URL 模拟 github 地址
    url = "file://" + str(repo).replace("\\", "/")
    mirrors = {"gh_proxy": False, "use_proxy": False, "hf_mirror": False}
    logs = []
    info = plugin_manager.clone_plugin(str(fake), url, mirrors=mirrors,
                                       progress=logs.append)
    check("克隆成功", info.path == str(fake / "custom_nodes" / "MyPlugin"),
          info.path)
    check("目录名取自 URL 末段", Path(info.path).name == "MyPlugin")
    check("插件文件就位", (Path(info.path) / "__init__.py").exists())
    check("has_requirements 检测到", info.has_requirements)
    check("远程地址已记录", "MyPlugin" in info.remote)

    # 4. 重复克隆 → 应报错
    try:
        plugin_manager.clone_plugin(str(fake), url, mirrors=mirrors)
        check("重复克隆被拒绝", False, "未报错")
    except RuntimeError as e:
        check("重复克隆被拒绝", "已存在" in str(e), str(e))

    # 5. 扫描识别
    plugins = plugin_manager.scan_plugins(str(fake))
    names = {p.name: p for p in plugins}
    check("扫描识别克隆的插件", "MyPlugin" in names and names["MyPlugin"].is_git,
          str(names))

    # 6. 目录名推导（_clone_target 纯函数，用不与已克隆插件冲突的名字）
    base = Path(str(fake)) / "custom_nodes"
    t1 = plugin_manager._clone_target(
        base, "https://github.com/user/OtherPlugin.git", "")
    check("URL 末段取名并去 .git", t1.name == "OtherPlugin", t1.name)
    t2 = plugin_manager._clone_target(
        base, "https://github.com/user/ThirdPlugin/", "")
    check("URL 尾斜杠处理", t2.name == "ThirdPlugin", t2.name)
    t3 = plugin_manager._clone_target(
        base, "https://github.com/user/Fourth.git", "自定义名")
    check("显式 name 优先", t3.name == "自定义名", t3.name)
    print("==")
    print(f"CLONE TEST: passed={passed} failed={failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
