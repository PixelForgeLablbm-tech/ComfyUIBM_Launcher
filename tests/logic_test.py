# -*- coding: utf-8 -*-
"""核心逻辑测试：配置 / 实例 / 参数构建 / git 更新管线 / 版本列表 / 插件 / 模型。

不依赖 PyQt5（launcher/args、system_info、mirrors、updater、plugin_manager、
model_manager 均无 UI 依赖），使用临时目录与真实 git 仓库做端到端验证。

用法: python tests/logic_test.py
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from launcher.config import Config                 # noqa: E402
from launcher.instance import Instance             # noqa: E402
from launcher import args as args_mod              # noqa: E402
from launcher import git_utils, updater            # noqa: E402
from launcher import mirrors                       # noqa: E402
from launcher import plugin_manager, model_manager  # noqa: E402
from launcher import instance_scanner              # noqa: E402
from launcher.system_info import clean_log_chunk   # noqa: E402
from launcher.self_update import has_update, _parse_version  # noqa: E402

# 测试临时目录必须位于工作区内（沙箱只允许写工作区），
# 且必须用 Path.mkdir 创建（tempfile.mkdtemp 创建的目录在沙箱下不可写）
TEST_ROOT = ROOT / ".logic_test_tmp"
TEST_ROOT.mkdir(exist_ok=True)
TMP = TEST_ROOT / f"case_{int(time.time() * 1000)}"
TMP.mkdir()

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def sh(cwd, *args):
    # Windows 反斜杠路径会被 git 误判为协议，统一转正斜杠
    def fix(p):
        return str(p).replace("\\", "/") if isinstance(p, (Path, str)) else p
    cmd = ["git", *[fix(a) for a in args]]
    return subprocess.run(cmd, cwd=fix(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          creationflags=NO_WINDOW, check=True)


def git(path, *args):
    return sh(path, *args)


passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


CAN_SHELL = None


def shell_ok() -> bool:
    """探测 git 能否通过 shell 派生 receive-pack（沙箱会禁止管道创建）。"""
    global CAN_SHELL
    if CAN_SHELL is not None:
        return CAN_SHELL
    try:
        r0 = TMP / "shellprobe"
        r0.mkdir()
        b0 = (TMP / "shellprobe.git").as_posix()
        (r0 / "f").write_text("x", encoding="utf-8")
        git(r0, "init")
        git(r0, "config", "user.email", "t@t")
        git(r0, "config", "user.name", "t")
        git(r0, "add", ".")
        git(r0, "commit", "-m", "p")
        git(r0, "init", "--bare", b0)
        git(r0, "remote", "add", "origin", "file://" + b0)
        git(r0, "push", "-u", "origin", git_utils.current_branch(r0))
        CAN_SHELL = True
    except Exception as e:
        CAN_SHELL = False
        print(f"  (当前环境禁止 git 经 shell 传输，远端更新用例将跳过: {e})")
    return CAN_SHELL


def main():
    print("== 配置读写与归一化 ==")
    cfg_path = TMP / "config.json"
    cfg = Config(cfg_path)
    cfg.settings["python_path"] = "python3"
    inst = Instance(name="测试机", type="local", path="C:/comfy")
    cfg.instances.append(inst.to_dict())
    cfg.current_instance_id = inst.uid
    check("config.save", cfg.save())
    cfg2 = Config(cfg_path)
    check("config reload", cfg2.instances and cfg2.instances[0]["name"] == "测试机")
    check("current_instance_id 持久化",
          cfg2.current_instance_id == inst.uid)
    check("launch 默认值归一化",
          cfg2.launch.get("port") == 8188 and
          cfg2.launch.get("mode") == "normalvram" and
          cfg2.launch.get("auto_restart") is False)
    check("mirrors 默认值归一化",
          cfg2.mirrors.get("pypi_mirror") == "aliyun")
    check("instance roundtrip",
          Instance.from_dict(cfg2.instances[0]).uid == inst.uid)

    print("== 启动参数构建 ==")
    launch = {"mode": "lowvram", "port": 9000, "listen": True,
              "force_fp16": True, "attention": "split", "cuda_device": 1,
              "extra_args": ["--disable-metadata"], "auto_restart": True}
    a = args_mod.build_args(launch, "--multi-user")
    check("mode/port/listen", "--lowvram" in a and "--port" in a and
          "9000" in a and "--listen" in a, str(a))
    check("fp16/attention/gpu", "--force-fp16" in a and
          "--use-split-cross-attention" in a and
          "--cuda-device" in a and "1" in a)
    check("额外参数合并", "--disable-metadata" in a and "--multi-user" in a)
    a2 = args_mod.build_args({"mode": "normalvram", "port": 8188}, "")
    check("normalvram 不传参", "--normalvram" not in a2 and "--lowvram" not in a2,
          str(a2))
    # 参数版本适配
    supported = {"--port", "--listen", "--cpu"}
    out, dropped = args_mod.filter_unsupported(a, supported)
    check("过滤不支持的参数", "--lowvram" in dropped and "--port" in out
          and "--listen" in out, f"{out}/{dropped}")

    print("== 日志清理 / 镜像 ==")
    check("ANSI 清理", clean_log_chunk("\x1b[32mhello\x1b[0m") == ["hello"])
    check("\\r 拆分", clean_log_chunk("a\rb") == ["a", "b"])
    extra, env = mirrors.git_extra_and_env(
        {"gh_proxy": True, "gh_proxy_prefix": "https://gh-proxy.com/",
         "use_proxy": True, "proxy": "http://127.0.0.1:7890"})
    check("GH 加速参数注入", any("insteadOf" in x for x in extra), str(extra))
    check("代理环境变量", env.get("HTTPS_PROXY") == "http://127.0.0.1:7890")
    check("PyPI 镜像", mirrors.pypi_mirror_url("aliyun") is not None and
          mirrors.pypi_mirror_url("official") is None)

    print("== git 版本更新管线 ==")
    repo = TMP / "comfy"
    repo.mkdir()
    (repo / "main.py").write_text("print('comfy')", encoding="utf-8")
    (repo / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    git(repo, "init")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "v1 初始版本")
    git(repo, "tag", "v0.1.0")
    branch = git_utils.current_branch(repo)
    check("git init branch detected", bool(branch), f"branch={branch}")
    check("is_git_repo", git_utils.is_git_repo(repo))
    check("short_commit", len(git_utils.short_commit(repo) or "") >= 7)
    check("remote_url none", git_utils.remote_url(repo) is None)
    check("is_dirty False", not git_utils.is_dirty(str(repo)))

    bare = TMP / "origin.git"
    sh(repo, "init", "--bare", str(bare))
    git(repo, "remote", "add", "origin", "file://" + str(bare).replace("\\", "/"))
    cn = repo / "custom_nodes"
    cn.mkdir(parents=True)

    if not shell_ok():
        info = updater.check_update(str(repo), fetch=False)
        check("check: 无远端分支时优雅报错", not info.ok and bool(info.error),
              info.error)
    else:
        git(repo, "push", "-u", "origin", branch)
        git(repo, "push", "origin", "--tags")
        git(TMP, "clone", str(bare), str(cn / "git_node"))

        info = updater.check_update(str(repo), fetch=False)
        check("check: 无更新", info.ok and not info.has_update and info.is_git,
              info.error)

        # 版本列表
        info_ver = updater.list_versions(
            Instance(name="x", path=str(repo)), {})
        tag_names = [t["name"] for t in info_ver["tags"]]
        check("版本列表含 v0.1.0", "v0.1.0" in tag_names, str(tag_names))

        # 在另一处克隆并提交新版本，打新 tag 后推回
        clone = TMP / "dev"
        git(TMP, "clone", str(bare), str(clone))
        git(clone, "config", "user.email", "t@t")
        git(clone, "config", "user.name", "t")
        (clone / "main.py").write_text("print('comfy v2')", encoding="utf-8")
        git(clone, "add", ".")
        git(clone, "commit", "-m", "v2 修复 bug")
        git(clone, "tag", "v0.2.0")
        git(clone, "push")
        git(clone, "push", "origin", "--tags")

        info2 = updater.check_update(str(repo), fetch=True)
        check("check: 发现更新",
              info2.ok and info2.has_update and info2.behind >= 1,
              f"ok={info2.ok} has={info2.has_update} behind={info2.behind} err={info2.error}")
        check("changelog 包含 v2", "v2" in info2.changelog, info2.changelog)

        ok, msg = updater.pull(str(repo))
        check("pull 成功", ok, msg)
        info3 = updater.check_update(str(repo), fetch=False)
        check("pull 后已最新", not info3.has_update)

        # 版本列表（清缓存后）应含 v0.2.0 且为最新
        updater._VERSION_CACHE.update(key=None, at=0.0, info=None)
        inst_local = Instance(name="测试", type="local", path=str(repo))
        info_ver2 = updater.list_versions(inst_local, {})
        tag_names2 = [t["name"] for t in info_ver2["tags"]]
        check("版本列表 v0.2.0 最新",
              tag_names2 == ["v0.2.0", "v0.1.0"] or
              (tag_names2[0] == "v0.2.0" and len(tag_names2) >= 2),
              str(tag_names2))
        check("latest_tag 正确", info_ver2["latest_tag"] == "v0.2.0")

        # 回滚到 v0.1.0（requirements 无变化 → 跳过依赖安装）
        updater.update_to(inst_local, "v0.1.0", {})
        check("回滚到 v0.1.0", updater.version(str(repo)).startswith("v0.1.0"),
              updater.version(str(repo)))
        # 更新回 v0.2.0
        updater.update_to(inst_local, "v0.2.0", {})
        check("更新到 v0.2.0", updater.version(str(repo)).startswith("v0.2.0"),
              updater.version(str(repo)))

    print("== 插件扫描 ==")
    (cn / "plain_node").mkdir(exist_ok=True)
    (cn / "plain_node" / "__init__.py").write_text("", encoding="utf-8")
    gnode = cn / "git_node"
    if not gnode.exists():
        gnode.mkdir()
        (gnode / "__init__.py").write_text("", encoding="utf-8")
        git(gnode, "init")
        git(gnode, "config", "user.email", "t@t")
        git(gnode, "config", "user.name", "t")
        git(gnode, "add", ".")
        git(gnode, "commit", "-m", "init")
        git(gnode, "remote", "add", "origin", "file://" + str(bare).replace("\\", "/"))
    plugins = plugin_manager.scan_plugins(str(repo))
    names = {p.name: p for p in plugins}
    check("扫描到 2 个插件", len(plugins) == 2, str(names))
    check("plain_node 非 git", not names["plain_node"].is_git)
    check("git_node 是 git", names["git_node"].is_git and
          names["git_node"].remote.replace("\\", "/").endswith("origin.git"),
          names["git_node"].remote)
    check("has_requirements 检测",
          names["plain_node"].has_requirements is False)

    if shell_ok():
        checked = plugin_manager.check_plugin_updates(plugins)
        by_name = {p.name: p for p in checked}
        check("git_node 可更新", by_name["git_node"].has_update)
        plugin_manager.update_plugin(by_name["git_node"])
        check("git_node 更新后最新", not by_name["git_node"].has_update)
    else:
        print("  (跳过插件远端更新用例)")

    print("== 实例扫描识别 ==")
    fake_main_only = TMP / "scan_only_main"
    fake_main_only.mkdir()
    (fake_main_only / "main.py").write_text("", encoding="utf-8")
    fake_comfy = TMP / "scan_comfy"
    fake_comfy.mkdir()
    (fake_comfy / "main.py").write_text("", encoding="utf-8")
    (fake_comfy / "models").mkdir()
    (fake_comfy / "comfy").mkdir()
    check("只有 main.py 不识别为 ComfyUI",
          not instance_scanner.is_comfyui_dir(fake_main_only))
    check("带 comfy/models 特征目录识别",
          instance_scanner.is_comfyui_dir(fake_comfy))
    check("缺 main.py 不识别",
          not instance_scanner.is_comfyui_dir(TMP))
    # probe 校验：添加实例时拒绝非 ComfyUI 目录
    try:
        instance_scanner.probe(str(fake_main_only))
        check("probe 拒绝非 ComfyUI 目录", False, "未抛错")
    except ValueError:
        check("probe 拒绝非 ComfyUI 目录", True)
    probed = instance_scanner.probe(str(fake_comfy))
    check("probe 接受真实 ComfyUI 并识别 python",
          probed["path"] == str(fake_comfy) and
          (probed["python"] or "python").strip() != "",
          str(probed))

    print("== 启动器自身更新判断 ==")
    check("版本解析", _parse_version("v1.2.3") == (1, 2, 3) and
          _parse_version("1.0.0") == (1, 0, 0))
    check("新版本判定", has_update("1.0.0", "v1.1.0") is True and
          has_update("1.1.0", "v1.1.0") is False and
          has_update("1.2.0", "v1.1.0") is False and
          has_update("1.0.0", "1.0.1") is True)

    print("== 模型分类与导入 ==")
    models = repo / "models"
    (models / "checkpoints").mkdir(parents=True)
    (models / "loras").mkdir()
    (models / "mystyle").mkdir()          # 非预设自定义目录
    (models / "mystyle" / "custom.safetensors").write_bytes(b"w" * 512)
    (models / "checkpoints" / "sd15.safetensors").write_bytes(b"x" * 2048)
    (models / "checkpoints" / "sub").mkdir()
    (models / "checkpoints" / "sub" / "nested.ckpt").write_bytes(b"y" * 1024)
    summary = model_manager.category_summary(str(repo))
    by_cat = {c["category"]: c for c in summary}
    check("分类统计含 checkpoints", "checkpoints" in by_cat and
          by_cat["checkpoints"]["count"] == 2, str(by_cat.get("checkpoints")))
    check("自定义目录直接列出", "mystyle" in by_cat and
          by_cat["mystyle"]["count"] == 1, str(list(by_cat)))
    check("不使用预设名（checkpoints 原样显示）",
          by_cat["checkpoints"]["label"].startswith("checkpoints"),
          by_cat["checkpoints"]["label"])
    check("不存在的目录不显示", "vae" not in by_cat, str(list(by_cat)))
    check("分类标签含数量与大小", "2" in by_cat["checkpoints"]["label"] and
          "KB" in by_cat["checkpoints"]["label"], by_cat["checkpoints"]["label"])
    check("human_size", model_manager.human_size(2048) == "2.00 KB",
          model_manager.human_size(2048))
    # 导入：同名自动改名 _1
    src = TMP / "src_model.safetensors"
    src.write_bytes(b"z" * 1024)
    ok_n, skip_n, copied = model_manager.import_models(
        [str(src), str(src)], str(models / "loras"))
    check("导入 2 个", ok_n == 2 and skip_n == 0, f"{ok_n}/{skip_n}")
    check("同名自动改名", copied[0] == "src_model.safetensors" and
          copied[1] == "src_model_1.safetensors", str(copied))
    check("原文件保留", src.exists())

    print("==")
    print(f"RESULT: passed={passed} failed={failed}")
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
