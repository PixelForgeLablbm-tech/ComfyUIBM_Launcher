# -*- coding: utf-8 -*-
"""内核维护：为当前实例的 Python 环境安装核心组件（Torch/xformers 等）。
也负责识别当前环境：显卡 / Python / ComfyUI / torch / sageattention / triton。

安装采用「事务式」策略，保证安装失败时**不破坏原有版本**：
  1. 预检（pip install --dry-run）：版本不存在 / Python 不兼容 / 依赖冲突
     在预检阶段即暴露，此时环境一个字节都不会被改动；
  2. 快照：记录目标包当前的精确版本与来源索引（+cuXXX 反推），并写入手动恢复清单；
  3. 安装（pip 输出实时滚动，进度可见）；
  4. 验证：torch 三件套装完后 import 验证，验证不通过视为失败；
  5. 失败自动回滚：--force-reinstall --no-deps 恢复原版本（优先命中 pip 缓存）；
     回滚失败则给出快照文件与手动恢复命令。"""
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import system_info
from .git_utils import NO_WINDOW
from .mirrors import pip_env, pip_index_args

KERNEL_PKGS = ("torch", "torchvision", "torchaudio")

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-Za-z]")

# import 验证脚本（在实例 Python 中执行，避免 GUI 崩溃）
VERIFY_SCRIPT = """# -*- coding: utf-8 -*-
import sys
out = []
try:
    import torch
    out.append("torch=" + torch.__version__)
except Exception as e:
    print("VERIFY_FAIL: import torch: %r" % (e,))
    sys.exit(1)
for mod in ("torchvision", "torchaudio"):
    try:
        m = __import__(mod)
        out.append("%s=%s" % (mod, m.__version__))
    except Exception as e:
        print("VERIFY_FAIL: import %s: %r" % (mod, e))
        sys.exit(1)
try:
    out.append("cuda=" + str(torch.cuda.is_available()))
except Exception:
    out.append("cuda=unknown")
print("VERIFY_OK")
print("; ".join(out))
"""


# ---------------------------------------------------------------- 基础工具
def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _clean_pip_line(s: str) -> str:
    return _ANSI_RE.sub("", s).strip()


def _run(python, args, timeout=30, cwd=None):
    try:
        proc = subprocess.run(
            [python] + args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd,
            creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        out = (proc.stdout or "").strip().splitlines()
        return proc.returncode, (out[0].strip() if out else ""), \
            (proc.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def _run_full(python, args, timeout=30, cwd=None):
    """返回 (returncode, stdout全文, stderr全文)。"""
    try:
        proc = subprocess.run(
            [python] + args, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd,
            creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except Exception as e:
        return -1, "", str(e)


def _stream_pip(python, args, env, cwd, progress, timeout):
    """运行 pip 并逐行转发输出到 progress（实时可见）。

    返回 (returncode, 完整输出文本)。超时自动 kill。
    """
    proc = subprocess.Popen(
        [python] + args, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False,
        creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    q = queue.Queue()

    def _reader():
        try:
            for raw in proc.stdout:
                q.put(raw)
        except Exception:
            pass
        finally:
            q.put(None)

    threading.Thread(target=_reader, daemon=True).start()

    out_lines = []
    buf = b""
    last_line = None
    dup = 0
    deadline = time.time() + timeout
    while True:
        try:
            raw = q.get(timeout=0.5)
        except queue.Empty:
            if time.time() > deadline:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                msg = f"安装超时（超过 {timeout // 60} 分钟），已终止"
                out_lines.append(msg)
                if progress:
                    progress("⏰ " + msg)
                return -1, "\n".join(out_lines)
            continue
        if raw is None:
            break
        buf += raw
        while True:
            n = buf.find(b"\n")
            r = buf.find(b"\r")
            idx = -1
            if n >= 0 and (r < 0 or n < r):
                idx = n
            elif r >= 0:
                idx = r
            if idx < 0:
                break
            line = _clean_pip_line(_decode(buf[:idx]))
            buf = buf[idx + 1:]
            if not line:
                continue
            out_lines.append(line)
            if line == last_line:
                dup += 1
                if dup <= 1 and progress:      # 重复行（进度条刷新）只播一次
                    progress(line)
            else:
                dup = 0
                last_line = line
                if progress:
                    progress(line)
    if buf:
        line = _clean_pip_line(_decode(buf))
        if line:
            out_lines.append(line)
            if progress:
                progress(line)
    proc.wait()
    rc = proc.returncode if proc.returncode is not None else 0
    return rc, "\n".join(out_lines)


def _analyze_failure(out: str) -> str:
    """从 pip 输出推断失败原因。"""
    low = out.lower()
    if not out.strip():
        return "未知错误（无任何输出）"
    if "network is unreachable" in low or "connection timed out" in low \
            or "read timed out" in low:
        return "网络连接失败：无法访问软件源，请检查网络或开启代理后重试"
    if "ssl" in low and ("eof" in low or "certificate" in low):
        return "网络连接不稳定（SSL 中断）：请重试，或更换网络后重试"
    if "no space left" in low or ("disk" in low and "space" in low):
        return "磁盘空间不足：torch 需要 ≥5GB 空间，请清理磁盘后重试"
    if "permission denied" in low or "access is denied" in low:
        return "权限不足：请以管理员身份运行启动器，或确认文件未被占用"
    if "no matching distribution" in low or "could not find a version" in low:
        m = re.search(r"requirement (\S+)", out)
        pkg = m.group(1) if m else "该包"
        py_m = re.search(r"from versions: ([^)]{0,200})", out)
        avail = f"（索引中可用：{py_m.group(1).strip()}）" if py_m else ""
        return f"找不到匹配版本：{pkg} 在当前 Python 版本下没有可用轮子{avail}，请换一个版本"
    if "not a valid wheel" in low:
        return "下载的安装包不完整（wheel 损坏），请重试"
    if "4096" in low or "connection reset" in low or "eof occurred" in low \
            or "unexpected eof" in low:
        return "下载中断：网络不稳定导致大文件下载失败，请重试"
    if "conflicting dependencies" in low or "dependency conflict" in low:
        return "依赖冲突：所选版本与当前环境不兼容"
    return "安装失败（详见安装日志）"


def _write_log(text: str) -> str:
    """把完整 pip 输出写入日志文件，返回路径。"""
    log_path = Path(tempfile.gettempdir()) / "ComfyUIBM_kernel_install.log"
    try:
        log_path.write_text(text, encoding="utf-8", errors="replace")
        return str(log_path)
    except Exception:
        return ""


# ---------------------------------------------------------------- 事务式安装
def _spec_names(spec: str) -> list:
    """从 pip 规格字符串提取包名列表，如 "sageattention==2.2.0" → ["sageattention"]。"""
    out = []
    for tok in spec.split():
        tok = tok.strip()
        if not tok or tok.startswith("-"):
            continue
        name = re.split(r"[=<>!~]", tok, 1)[0]
        if name and re.match(r"^[A-Za-z0-9_.-]+$", name):
            out.append(name)
    return out


def _torch_pair(torch_ver: str):
    """torch 版本 → (torchvision, torchaudio) 配套版本（PyTorch 官方同组发布）。
    torch 2.x.y → torchvision 0.(x+15).y，torchaudio 与 torch 同号。"""
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", torch_ver or "")
    if not m:
        return "", ""
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if major != 2:
        return "", ""
    return f"0.{minor + 15}.{patch}", torch_ver


def _cu_index_from_version(ver: str) -> str:
    """从 torch 版本号反推其来源索引："2.7.1+cu126" → cu126 索引 URL。"""
    m = re.search(r"\+cu(\d+)", ver or "")
    return f"https://download.pytorch.org/whl/cu{m.group(1)}" if m else ""


def _direct_urls(python, names):
    """读各包 direct_url.json 的来源 URL（仅保留 wheel 直链，供回滚用）。
    返回 {包名: url}。索引安装（无 .whl URL）忽略。"""
    if not names:
        return {}
    code = (
        "import sys, json, importlib.metadata as m\n"
        "for n in sys.argv[1:]:\n"
        "    try:\n"
        "        d = m.distribution(n)\n"
        "        t = d.read_text('direct_url.json')\n"
        "        if t:\n"
        "            u = (json.loads(t) or {}).get('url', '')\n"
        "            if u:\n"
        "                print(n + '|' + u)\n"
        "    except Exception:\n"
        "        pass\n"
    )
    rc, out, _ = _run_full(python, ["-c", code] + list(names), timeout=60)
    res = {}
    for line in (out or "").splitlines():
        if "|" not in line:
            continue
        n, u = line.split("|", 1)
        u = u.strip()
        # 只认 wheel 直链（file:// 或 http(s) 以 .whl 结尾）；
        # 索引安装的 direct_url 是目录/索引地址，不能用于回滚
        if u.lower().endswith(".whl") or u.lower().startswith("file://"):
            res[n.strip().lower()] = u
    return res


def _snapshot_packages(python, names, cwd):
    """记录目标包当前版本与来源 URL（wheel 直链）；写手动恢复清单文件。"""
    data = {}
    rc, out, _ = _run_full(
        python, ["-m", "pip", "show"] + list(names), timeout=60, cwd=cwd)
    wanted = {n.lower() for n in names}
    for block in re.split(r"\n\s*\n", out or ""):
        nm = re.search(r"(?m)^Name:\s*(\S+)", block)
        ver = re.search(r"(?m)^Version:\s*(\S+)", block)
        if nm and ver and nm.group(1).lower() in wanted \
                and ver.group(1) != "None":
            data[nm.group(1).lower()] = {"version": ver.group(1), "url": ""}
    for name, url in _direct_urls(python, list(data.keys())).items():
        if name in data:
            data[name]["url"] = url
    index = ""
    if "torch" in data:
        old_idx = _cu_index_from_version(data["torch"]["version"])
        index = old_idx or ""       # CPU 版（无 +cu）回滚走默认源
    snap_file = None
    try:
        lines = []
        for n, info in data.items():
            if info["url"]:
                lines.append(info["url"])       # 直链：pip -r 可直接装
            else:
                lines.append(f"{n}=={info['version']}")
        if lines:
            fd, snap_file = tempfile.mkstemp(
                suffix=".txt", prefix="ComfyUIBM_kernel_snapshot_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
    except Exception:
        snap_file = None
    return {"pkgs": data, "index": index, "file": snap_file,
            "names": list(names)}


def _rollback(python, snapshot, env, cwd, progress, mirrors=None):
    """恢复快照版本。优先用原 wheel 直链重装（GitHub 轮子不在任何 pip 索引上），
    否则按版本号 + 原索引恢复。返回 (ok, 说明文本)。"""
    pkgs = snapshot.get("pkgs") or {}
    index = snapshot.get("index") or ""
    names = snapshot.get("names") or list(pkgs.keys())
    if not pkgs:
        # 原环境没有这些包 → 卸载残留即可
        if progress:
            progress("↩️ 原环境未安装这些包，正在清理…")
        rc, _out = _stream_pip(
            python, ["-m", "pip", "uninstall", "-y"] + names,
            env, cwd, progress, 300)
        return rc == 0, "已清理残留"
    specs = []
    for n, info in pkgs.items():
        if isinstance(info, dict):
            url = info.get("url") or ""
            ver = info.get("version") or ""
        else:
            url, ver = "", info          # 兼容旧格式快照
        if url:
            # 直链轮子先（带加速）下载到本地再装，避免 pip 直连 GitHub 超时
            dest = Path(tempfile.gettempdir()) / urllib.parse.unquote(
                url.split("?")[0].split("/")[-1])
            _download_file(url, dest, progress, mirrors=mirrors)
            specs.append(str(dest))
        elif ver:
            specs.append(f"{n}=={ver}")
    args = ["-m", "pip", "install", "--force-reinstall", "--no-deps"] + specs
    if index:
        args += ["--index-url", index]
    if progress:
        progress("↩️ 正在恢复原版本（优先使用本地缓存）…")
    rc, out = _stream_pip(python, args, env, cwd, progress, 1800)
    if rc != 0:
        return False, _analyze_failure(out)
    return True, "已恢复原版本"


def _fail_and_rollback(python, snapshot, env, cwd, progress, reason, pip_out,
                       mirrors=None):
    """安装失败：自动回滚；回滚失败给出快照文件与手动命令。抛 RuntimeError。"""
    _write_log(pip_out)
    ok, rmsg = False, ""
    try:
        ok, rmsg = _rollback(python, snapshot, env, cwd, progress,
                             mirrors=mirrors)
    except Exception as e:
        ok, rmsg = False, f"回滚异常：{e}"
    msg = reason
    if ok:
        msg += f"\n✅ 已自动恢复原版本（{rmsg}），你的环境没有被破坏。"
    else:
        msg += f"\n❌ 自动回滚失败：{rmsg}"
        snap_file = snapshot.get("file")
        if snap_file and Path(snap_file).exists():
            msg += (f"\n原版本清单已保存：{snap_file}\n"
                    f"可手动恢复：python -m pip install --force-reinstall "
                    f"-r \"{snap_file}\"")
        else:
            msg += "\n（无快照文件，无法提供手动恢复清单）"
    if pip_out:
        msg += f"\n\n失败原因分析：{_analyze_failure(pip_out)}"
    raise RuntimeError(msg)


def _pip_dry_run(python, args, env, cwd, progress, timeout=900):
    """预检：pip install --dry-run 解析版本与依赖，不改动环境。

    返回 (ok, 失败原因, pip 输出尾部)。失败时把完整输出写入日志，
    并实时转发 pip 输出到 progress，用户能看到预检到底卡在哪。
    旧版 pip 不支持 --dry-run 时跳过预检（返回 ok）。
    """
    dry = list(args)
    try:
        i = dry.index("install")
    except ValueError:
        return True, "", ""
    dry.insert(i + 1, "--dry-run")
    dry.append("--only-binary=:all:")
    if progress:
        progress("⏳ 预检中：解析版本与依赖（不会改动环境）…")
    rc, out = _stream_pip(python, dry, env, cwd, progress, timeout)
    low = out.lower()
    if "no such option" in low or "unrecognized" in low:
        return True, "", ""             # 旧版 pip：跳过预检
    if rc == 0:
        return True, "", ""
    _write_log(out)
    lines = [l for l in out.splitlines() if l.strip()]
    tail = "\n".join(lines[-10:])
    return False, _analyze_failure(out), tail


def _run_py_script(python, code, cwd, timeout=300):
    """把脚本写入临时文件执行，返回 (rc, stdout全文, stderr全文)。"""
    fd, path = tempfile.mkstemp(suffix=".py", prefix="comfyibm_check_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
        return _run_full(python, [path], timeout=timeout, cwd=cwd)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def _verify_kernel(python, cwd, progress):
    """安装后 import 验证 torch 三件套。返回 (ok, 详情文本)。"""
    rc, out, _ = _run_py_script(python, VERIFY_SCRIPT, cwd, 300)
    if rc == 0 and "VERIFY_OK" in (out or ""):
        detail = re.sub(r"VERIFY_OK\s*;?\s*", "", out or "").strip()
        return True, detail or "导入正常"
    reason = out.strip() or "验证失败"
    return False, reason


SAGEATTN_VERIFY_SCRIPT = """# -*- coding: utf-8 -*-
import sys
import torch
try:
    from sageattention import sageattn
except Exception as e:
    print("VERIFY_FAIL: import sageattention: %r" % (e,))
    sys.exit(1)
print("SA_IMPORT_OK")
if torch.cuda.is_available():
    try:
        q = torch.randn(1, 8, 128, 64, device="cuda", dtype=torch.float16)
        k, v = q.clone(), q.clone()
        out = sageattn(q, k, v)
        torch.cuda.synchronize()
        print("SA_RUN_OK shape=%s" % (tuple(out.shape),))
    except Exception as e:
        msg = str(e)
        if "Unsupported CUDA architecture" in msg:
            import re
            mm = re.search(r"sm\\d+", msg)
            print("VERIFY_FAIL: 显卡架构 %s 不受 sageattention 支持"
                  "（需要 sm75+ / Turing 及以上）" % (mm.group(0) if mm else "?"))
        else:
            print("VERIFY_FAIL: CUDA 内核实测失败: %r" % (e,))
        sys.exit(1)
else:
    print("SA_RUN_OK cpu-only")
"""


def _verify_sageattention(python, cwd, progress):
    """sageattention 验证：import + 真实 CUDA 内核实测（能发现
    "Unsupported CUDA architecture" 这类 import 检查不到的兼容问题）。"""
    rc, out, _ = _run_py_script(python, SAGEATTN_VERIFY_SCRIPT, cwd, 600)
    text = out or ""
    if rc == 0 and "SA_RUN_OK" in text:
        return True, "import + CUDA 内核实测正常"
    lines = [l for l in text.splitlines() if l.strip()]
    return False, (lines[-1] if lines else "sageattention 验证失败")


def _run_transaction(python, args, env, cwd, progress, names, label,
                     timeout, verify=None, mirrors=None):
    """事务式安装：预检 → 快照 → 安装（实时输出）→ 验证 → 失败自动回滚。

    verify: 可选的回调 verify(python, cwd, progress) -> (ok, detail)；
            提供则装后执行，失败同样回滚。torch 三件套默认走 import 验证。
    mirrors: 透传给回滚（wheel 直链下载走 GitHub 加速）。
    """
    # 1. 预检：最常见的失败（版本不存在 / Python 不兼容 / 依赖冲突）
    #    在预检阶段暴露，环境不受任何影响。
    ok, why, tail = _pip_dry_run(python, args, env, cwd, progress)
    if not ok:
        msg = f"预检未通过（未改动任何环境）：{why}\n原版本保持不变。"
        if tail:
            msg = (f"预检未通过（未改动任何环境）：{why}\n\n"
                   f"预检输出：\n{tail}\n\n原版本保持不变。\n"
                   f"完整日志：{Path(tempfile.gettempdir()) / 'ComfyUIBM_kernel_install.log'}")
        raise RuntimeError(msg)

    # 2. 快照当前版本（含来源索引 + 手动恢复清单文件）
    #    回滚索引由旧 torch 的 +cu 后缀推导（_snapshot_packages 内完成），
    #    绝不能用"新装的索引"去回滚旧版本。
    snapshot = _snapshot_packages(python, names, cwd)
    old = "，".join(
        (f"{n}={info['version']}" if isinstance(info, dict) else f"{n}={info}")
        for n, info in snapshot["pkgs"].items()) or "未安装"
    if progress:
        progress(f"📦 当前版本：{old}")

    # 3. 正式安装（pip 输出实时滚动）
    rc, out = _stream_pip(python, args, env, cwd, progress, timeout)
    if rc != 0:
        _fail_and_rollback(
            python, snapshot, env, cwd, progress, f"{label} 安装失败", out,
            mirrors=mirrors)
        return

    # 4. 验证：装完必须能 import / 加载扩展，否则视为失败并回滚
    if verify is not None:
        if progress:
            progress("⏳ 安装完成，正在验证…")
        vok, detail = verify(python, cwd, progress)
        if not vok:
            _fail_and_rollback(
                python, snapshot, env, cwd, progress,
                f"{label} 安装后验证失败：{detail}", "", mirrors=mirrors)
            return
        if progress:
            progress(f"✅ 验证通过：{detail}")
    elif set(names) >= {"torch", "torchvision", "torchaudio"}:
        if progress:
            progress("⏳ 安装完成，正在验证导入…")
        vok, detail = _verify_kernel(python, cwd, progress)
        if not vok:
            _fail_and_rollback(
                python, snapshot, env, cwd, progress,
                f"{label} 安装后验证失败：{detail}", "", mirrors=mirrors)
            return
        if progress:
            progress(f"✅ 验证通过：{detail}")


# ---------------------------------------------------------------- 公开安装接口
def install_package(inst, spec: str, mirrors: dict, progress=None):
    """用当前实例的 Python 安装指定包（事务式，失败自动回滚）。

    spec: pip 包名或安装规格，如 "torch torchvision torchaudio"、"xformers"、
          "sageattention==2.2.0"。
    走 PyPI 镜像 / 代理 / HF 镜像环境（与「更新维护 → 安装依赖」一致）。
    失败抛 RuntimeError（含原因分析与回滚结果）。
    """
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    env = dict(os.environ)
    env.update(pip_env(mirrors))
    names = _spec_names(spec)
    args = ["-m", "pip", "install"] + pip_index_args(mirrors) + spec.split()
    if progress:
        progress(f"⏳ 安装：{spec}（可能需要几分钟，请耐心等待）…")
    _run_transaction(python, args, env, inst.path, progress, names,
                     label=spec, timeout=3600, mirrors=mirrors)


def install_torch(inst, cuda_suffix: str, mirrors: dict, progress=None,
                  version: str = ""):
    """从 PyTorch 官方索引安装 Torch 三件套（事务式，失败自动回滚）。

    cuda_suffix: "cu118" / "cu126" / "cu128" / "cu130" / "cu132"。
    version: 指定版本号（如 "2.7.1"），torchvision/torchaudio 自动按官方
             配套版本锁定，避免"torch 换了、vision 没配对"的残破状态；
             为空则安装该索引内最新版三件套。
    """
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    env = dict(os.environ)
    env.update(pip_env(mirrors))
    index = f"https://download.pytorch.org/whl/{cuda_suffix}"
    if version:
        tv, ta = _torch_pair(version)
        specs = [f"torch=={version}", f"torchvision=={tv}", f"torchaudio=={ta}"]
    else:
        specs = ["torch", "torchvision", "torchaudio"]
    args = ["-m", "pip", "install"] + specs + ["--index-url", index]
    if not version:
        args.append("--upgrade")   # 无版本约束时强制升级，避免"已满足"秒退
    label = f"Torch {version}（{cuda_suffix}）" if version \
        else f"最新 Torch（{cuda_suffix}）"
    if progress:
        progress(f"⏳ 安装：{label}（约 2GB，请耐心等待）…")
    _run_transaction(python, args, env, inst.path, progress,
                     ["torch", "torchvision", "torchaudio"],
                     label=label, timeout=7200)


# ---------------------------------------------------------------- 按 torch 匹配的 wheel 安装
# 参考 TE 启动器实测方法：xformers / SageAttention / llama-cpp 都用"预下载
# Windows 轮子 + pip install --no-deps"安装；但 TE 不看已装 torch 就装固定
# 轮子（导致 xformers/sageattention 装出 CUDA 不匹配的坏组合），这里补上
# 版本匹配 + 装后 import 验证 + 失败自动回滚。
def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "ComfyUIBM-Launcher/1.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _download_file(url, dest, progress, timeout=1800, mirrors=None):
    """流式下载到临时目录，返回本地路径；带 MB 进度提示。
    GitHub 直链自动走 gh-proxy 加速（配置开启时），失败自动重试。"""
    from .mirrors import gh_proxy_url
    url = gh_proxy_url(url, mirrors or {})
    tmp = str(dest) + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "ComfyUIBM-Launcher/1.1"})
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                last = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if progress and done - last >= 8 << 20:
                            last = done
                            total_txt = f"/{total // 1048576} MB" if total else ""
                            progress(f"⏳ 下载中：{done // 1048576} MB{total_txt}")
            os.replace(tmp, dest)
            return str(dest)
        except Exception as e:
            last_err = e
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            if progress and attempt < 2:
                progress(f"⚠ 下载中断（第 {attempt + 1} 次），正在重试…")
    raise RuntimeError(f"下载失败（已重试 3 次）：{last_err}")


def _ver_key(ver: str):
    """版本字符串 → 可比较元组（含 post）。"""
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", ver or "")
    if not m:
        return (0, 0, 0, 0)
    post = 0
    pm = re.search(r"\.post(\d+)", ver)
    if pm:
        post = int(pm.group(1))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), post)


def _ver_ge(ver, low) -> bool:
    return _ver_key(ver) >= _ver_key(low)


def _installed_torch(python):
    """返回 (torch 基础版本, cu 后缀)；未装返回 ("", "")。
    pip show 被损坏 dist-info 干扰（Version: None）时，回退用 import 取真实版本。"""
    ok, ver = _pip_show(python, "torch")
    if not ok or not ver:
        rc, out, _ = _run_full(
            python, ["-c", "import torch; print(torch.__version__)"],
            timeout=300)
        if rc == 0 and (out or "").strip():
            ver = out.strip().splitlines()[0].strip()
    if not ver or ver == "None":
        return "", ""
    base = re.split(r"\+", ver)[0]
    m = re.search(r"\+cu(\d+)", ver)
    cu = f"cu{m.group(1)}" if m else ""
    return base, cu


def _import_verify(modname, fail_marker=""):
    """构造 import 验证回调；fail_marker 命中（如 xformers 的
    "can't load C++/CUDA" 警告）也判定失败。"""
    def verify(python, cwd, progress):
        rc, out, err = _run_full(
            python, ["-c", f"import {modname}; print('{modname.upper()}_OK')"],
            timeout=300, cwd=cwd)
        text = (out or "") + (err or "")
        if rc == 0 and f"{modname.upper()}_OK" in text:
            return True, f"import {modname} 正常"
        if fail_marker and fail_marker.lower() in text.lower():
            return False, f"{modname} 的 CUDA/C++ 扩展无法加载（wheel 与 torch 不匹配）"
        lines = [l for l in text.splitlines() if l.strip()]
        return False, (lines[-1] if lines else f"{modname} import 失败")
    return verify


def _xformers_candidates():
    """PyPI 上所有带 torch 版本要求的 xformers Windows 轮子。
    返回 [{"version","url","torch"}]，按版本从新到旧。"""
    try:
        idx = _http_json("https://pypi.org/pypi/xformers/json", timeout=30)
    except Exception as e:
        raise RuntimeError(f"查询 PyPI xformers 信息失败：{e}")
    items = []
    versions = sorted(idx.get("releases", {}).keys(),
                      key=_ver_key, reverse=True)
    for v in versions[:12]:
        try:
            data = _http_json(f"https://pypi.org/pypi/xformers/{v}/json",
                              timeout=20)
        except Exception:
            continue
        torch_req = ""
        for r in (data.get("info", {}).get("requires_dist") or []):
            r = (r or "").replace(" ", "")
            m = re.match(r"torch==([\d.]+)", r)
            if m:
                torch_req = m.group(1)
                break
        for u in data.get("urls", []):
            if "win_amd64" in u.get("filename", ""):
                items.append({"version": v, "url": u["url"], "torch": torch_req})
    return items


def _match_xformers_wheel(torch_ver: str):
    """PyPI 上找依赖 torch==<torch_ver> 的 xformers Windows 轮子。
    返回 (版本, 下载URL) 或 None。"""
    for it in _xformers_candidates():
        if it["torch"] == torch_ver:
            return it["version"], it["url"]
    return None


def _sageattention_candidates():
    """woct0rdho/SageAttention Releases 全部 Windows 轮子（含匹配信息）。
    返回 [{"name","url","cu","torch_exact","torch_min","andhigher",
           "post","abi3","label"}]。"""
    try:
        rels = _http_json(
            "https://api.github.com/repos/woct0rdho/SageAttention/releases?per_page=20",
            timeout=30)
    except Exception as e:
        raise RuntimeError(f"查询 SageAttention 发布信息失败：{e}")
    items = []
    for rel in rels:
        tag = rel.get("tag_name", "") or ""
        if "windows" not in tag:
            continue
        post = 0
        pm = re.search(r"\.post(\d+)", tag)
        if pm:
            post = int(pm.group(1))
        for a in rel.get("assets", []):
            name = a.get("name", "") or ""
            if not name.endswith("win_amd64.whl"):
                continue
            m = re.search(r"\+cu(\d+)torch([\d.]+?)(andhigher)?\.?(?:post\d+)?-",
                          name)
            if not m:
                continue
            cu = f"cu{m.group(1)}"
            t = m.group(2)
            andhigher = bool(m.group(3))
            abi3 = 1 if "-abi3-" in name else 0
            range_txt = f"torch≥{t}" if andhigher else f"torch={t}"
            # 简短易读标签（完整文件名由 UI 作为悬停提示展示）
            ver = "2.2.0"
            vm = re.search(r"^sageattention-([\d.]+)", name)
            if vm:
                ver = vm.group(1)
            post_txt = f" post{post}" if post else ""
            if abi3:
                py_txt = "Py3.9+通用"
            else:
                cm = re.search(r"cp(\d\d\d)-cp\d\d\d", name)
                py_txt = (f"Py{cm.group(1)[0]}.{cm.group(1)[1:]}" if cm else "?")
            label = (f"SageAttention {ver}{post_txt}"
                     f"（{cu} / {range_txt} / {py_txt}）")
            items.append({
                "name": name, "url": a.get("browser_download_url", ""),
                "cu": cu, "torch_exact": t, "torch_min": t,
                "andhigher": andhigher, "post": post, "abi3": abi3,
                "label": label,
            })
    return items


def _pick_sage(cands, torch_ver, cu):
    """从候选里挑最佳：精确匹配 > andhigher 覆盖；同条件取最新 post；优先 abi3。"""
    best_i, best_key = None, None
    for i, it in enumerate(cands):
        if it["cu"] != cu:
            continue
        if it["andhigher"]:
            if not _ver_ge(torch_ver, it["torch_min"]):
                continue
            exact = 0
        else:
            if torch_ver != it["torch_exact"]:
                continue
            exact = 1
        key = (exact, it["post"], it["abi3"])
        if best_key is None or key > best_key:
            best_key, best_i = key, i
    return best_i


def _match_sageattention_wheel(torch_ver: str, cu: str):
    """找匹配 (torch, cu) 的轮子。返回 (下载URL, 文件名) 或 None。"""
    cands = _sageattention_candidates()
    i = _pick_sage(cands, torch_ver, cu)
    if i is None:
        return None
    return cands[i]["url"], cands[i]["name"]


def _llamacpp_candidates(pyver: str):
    """JamePeng/llama-cpp-python Releases 匹配 (Python 版本) 的 Windows 轮子。
    返回 [{"name","url","cu","py","version","label"}]。"""
    try:
        rels = _http_json(
            "https://api.github.com/repos/JamePeng/llama-cpp-python/releases?per_page=15",
            timeout=30)
    except Exception as e:
        raise RuntimeError(f"查询 llama-cpp-python 发布信息失败：{e}")
    items = []
    for rel in rels:
        tag = rel.get("tag_name", "") or ""
        if "-win-" not in tag:
            continue
        ver = tag.split("-")[0].lstrip("v")
        for a in rel.get("assets", []):
            name = a.get("name", "") or ""
            m = re.match(r"llama_cpp_python-[\d.]+(?:\+cu(\d+))?-cp(\d\d\d)-cp\d\d\d-win_amd64\.whl", name)
            if not m:
                continue
            cu = f"cu{m.group(1)}"
            py = m.group(2)
            if py != pyver:
                continue
            items.append({
                "name": name, "url": a.get("browser_download_url", ""),
                "cu": cu, "py": py, "version": ver,
                "label": f"llama-cpp-python {ver}（{cu} / Python {py[:1]}.{py[1:]}）",
            })
    return items


def _match_llamacpp_wheel(cu: str, pyver: str):
    """找匹配 (cu, Python 版本) 的轮子。返回 (下载URL, 文件名) 或 None。"""
    for it in _llamacpp_candidates(pyver):
        if it["cu"] == cu:
            return it["url"], it["name"]
    return None


def _install_wheel(inst, mirrors, progress, names, label, wheel_url,
                   verify=None, timeout=3600):
    """下载 wheel 到临时目录 → 事务式 pip install --no-deps。"""
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    env = dict(os.environ)
    env.update(pip_env(mirrors))
    # GitHub 会把文件名里的 + 编码成 %2B，必须解码，否则 pip 报
    # "Invalid wheel filename" 导致预检失败
    fname = urllib.parse.unquote(wheel_url.split("?")[0].split("/")[-1])
    dest = Path(tempfile.gettempdir()) / fname
    if progress:
        progress(f"⏳ 正在下载：{fname}")
    _download_file(wheel_url, dest, progress, mirrors=mirrors)
    args = ["-m", "pip", "install", "--no-deps", "-v", str(dest)]
    _run_transaction(python, args, env, inst.path, progress, names,
                     label=label, timeout=timeout, verify=verify,
                     mirrors=mirrors)


def install_xformers(inst, mirrors: dict, progress=None, url=""):
    """安装 xformers：按已装 torch 版本从 PyPI 选官方 Windows 轮子。
    url 非空时跳过匹配，直接安装用户选择的轮子。"""
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    base, cu = _installed_torch(python)
    if not base:
        raise RuntimeError("未检测到 torch，请先安装 Torch 再安装 xformers")
    if url:
        _install_wheel(inst, mirrors, progress, ["xformers"],
                       "xformers（手动选择）", url,
                       verify=_import_verify("xformers",
                                             fail_marker="can't load C++/CUDA"))
        return
    if progress:
        progress(f"⏳ 已装 torch {base}（{cu or '无 CUDA'}），查找匹配的 xformers Windows 轮子…")
    hit = _match_xformers_wheel(base)
    if not hit:
        raise RuntimeError(
            f"PyPI 没有提供匹配 torch=={base} 的 xformers Windows 轮子。\n"
            "xformers 官方 Windows 轮子与 torch 版本严格绑定，"
            "请先安装配套的 torch 版本。")
    ver, _url = hit
    _install_wheel(inst, mirrors, progress, ["xformers"],
                   f"xformers {ver}（torch {base}）", _url,
                   verify=_import_verify("xformers",
                                         fail_marker="can't load C++/CUDA"))


def install_sageattention(inst, mirrors: dict, progress=None, url=""):
    """安装 SageAttention 2.2：按 (torch 版本, CUDA) 从官方 GitHub Releases 选轮子。
    url 非空时跳过匹配，直接安装用户选择的轮子。"""
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    base, cu = _installed_torch(python)
    if not base:
        raise RuntimeError("未检测到 torch，请先安装 Torch 再安装 SageAttention")
    if url:
        _install_wheel(inst, mirrors, progress, ["sageattention"],
                       "SageAttention（手动选择）", url,
                       verify=_verify_sageattention)
        return
    if not cu:
        raise RuntimeError("当前 torch 为 CPU 版，SageAttention 需要 CUDA 版 torch")
    if progress:
        progress(f"⏳ 已装 torch {base}（{cu}），查找匹配的 SageAttention 轮子…")
    hit = _match_sageattention_wheel(base, cu)
    if not hit:
        raise RuntimeError(
            f"SageAttention 官方 Releases 没有匹配 torch {base} + {cu} 的 Windows 轮子。\n"
            "请换一个 torch 版本（如 cu128 + torch 2.7.x / 2.8.x）。")
    _url, name = hit
    _install_wheel(inst, mirrors, progress, ["sageattention"],
                   f"SageAttention {name}", _url,
                   verify=_verify_sageattention)


def install_llamacpp(inst, mirrors: dict, progress=None, url=""):
    """安装 llama-cpp-python：按 (CUDA, Python 版本) 从 JamePeng fork Releases 选轮子。
    url 非空时跳过匹配，直接安装用户选择的轮子。"""
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    base, cu = _installed_torch(python)
    if not base:
        raise RuntimeError("未检测到 torch，请先安装 Torch 再安装 llama-cpp")
    if url:
        _install_wheel(inst, mirrors, progress, ["llama-cpp-python"],
                       "llama-cpp-python（手动选择）", url,
                       verify=_import_verify("llama_cpp"))
        return
    if not cu:
        raise RuntimeError("当前 torch 为 CPU 版，llama-cpp 建议配合 CUDA 版 torch")
    rc, line, _ = _run(
        python, ["-c", "import sys; print('%d%d' % (sys.version_info.major, sys.version_info.minor))"])
    pyver = line.strip() if rc == 0 else ""
    if not pyver:
        raise RuntimeError("无法识别实例 Python 版本")
    if progress:
        progress(f"⏳ torch {base}（{cu}）+ Python {pyver[:1]}.{pyver[1:]}，查找匹配的 llama-cpp 轮子…")
    hit = _match_llamacpp_wheel(cu, pyver)
    if not hit:
        raise RuntimeError(
            f"JamePeng/llama-cpp-python Releases 没有匹配 {cu} + Python {pyver[:1]}.{pyver[1:]} 的 Windows 轮子。")
    _url, name = hit
    _install_wheel(inst, mirrors, progress, ["llama-cpp-python"],
                   f"llama-cpp-python {name}", _url,
                   verify=_import_verify("llama_cpp"))


def wheel_install_plan(inst, which: str):
    """获取安装候选方案（供 UI 弹窗选择）。

    which: "xformers" / "sageattention" / "llamacpp"。
    返回 {"title", "torch", "cu", "py", "items": [(label, url)...],
          "matched": 预选下标或 None}。
    """
    python = inst.resolve_python("python")
    if not python:
        raise RuntimeError("未找到 Python 解释器，请先在实例/设置中配置")
    base, cu = _installed_torch(python)
    rc, line, _ = _run(
        python, ["-c", "import sys; print('%d%d' % (sys.version_info.major, sys.version_info.minor))"])
    pyver = line.strip() if rc == 0 else ""
    plan = {"torch": base, "cu": cu, "py": pyver, "items": [], "matched": None}
    if which == "xformers":
        plan["title"] = "安装 xformers（按 torch 匹配，可手动改选）"
        if not base:
            raise RuntimeError("未检测到 torch，请先安装 Torch 再安装 xformers")
        cands = _xformers_candidates()
        plan["items"] = [(f"xformers {it['version']}（需 torch {it['torch'] or '未知'}）",
                          it["url"]) for it in cands]
        plan["matched"] = next(
            (i for i, it in enumerate(cands) if it["torch"] == base), None)
    elif which == "sageattention":
        plan["title"] = "安装 SageAttention（按 torch/CUDA 匹配，可手动改选）"
        if not base:
            raise RuntimeError("未检测到 torch，请先安装 Torch 再安装 SageAttention")
        cands = _sageattention_candidates()
        plan["items"] = [(it["label"], it["url"]) for it in cands]
        plan["matched"] = _pick_sage(cands, base, cu) if cu else None
    elif which == "llamacpp":
        plan["title"] = "安装 llama-cpp-python（JamePeng CUDA 版，可手动改选）"
        if not base:
            raise RuntimeError("未检测到 torch，请先安装 Torch 再安装 llama-cpp")
        if not pyver:
            raise RuntimeError("无法识别实例 Python 版本")
        cands = _llamacpp_candidates(pyver)
        plan["items"] = [(it["label"], it["url"]) for it in cands]
        plan["matched"] = next(
            (i for i, it in enumerate(cands) if it["cu"] == cu), None)
    return plan


# ---------------------------------------------------------------- 环境识别
def detect_cuda():
    """解析 nvidia-smi：返回 (driver_version, cuda_version) 或 (None, None)。

    driver: 如 "582.66"；cuda: 如 "13.0"（驱动支持的 CUDA 最高版本）。
    """
    try:
        proc = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            return None, None
        driver = None
        cuda = None
        for line in proc.stdout.splitlines():
            m = re.search(r"Driver Version:\s*([\d.]+)", line)
            if m:
                driver = m.group(1)
            m = re.search(r"CUDA Version:\s*([\d.]+)", line)
            if m:
                cuda = m.group(1)
        return driver, cuda
    except Exception:
        return None, None


# Torch 版本表：(显示名, PyTorch 官方索引后缀)
# 数据来自 https://download.pytorch.org/whl/<cu>/torch/（官方实际可下载组合）
TORCH_CHOICES = [
    # cu118（老显卡 GTX 10/16 系、RTX 20 系；仅 Python ≤3.11 有 2.0/2.1 轮子）
    ("Torch v2.0.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.0.1 (CUDA 11.8)", "cu118"),
    ("Torch v2.1.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.1.1 (CUDA 11.8)", "cu118"),
    ("Torch v2.1.2 (CUDA 11.8)", "cu118"),
    ("Torch v2.2.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.2.1 (CUDA 11.8)", "cu118"),
    ("Torch v2.2.2 (CUDA 11.8)", "cu118"),
    ("Torch v2.3.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.3.1 (CUDA 11.8)", "cu118"),
    ("Torch v2.4.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.4.1 (CUDA 11.8)", "cu118"),
    ("Torch v2.5.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.5.1 (CUDA 11.8)", "cu118"),
    ("Torch v2.6.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.7.0 (CUDA 11.8)", "cu118"),
    ("Torch v2.7.1 (CUDA 11.8)", "cu118"),
    # cu121
    ("Torch v2.1.0 (CUDA 12.1)", "cu121"),
    ("Torch v2.1.1 (CUDA 12.1)", "cu121"),
    ("Torch v2.1.2 (CUDA 12.1)", "cu121"),
    ("Torch v2.2.0 (CUDA 12.1)", "cu121"),
    ("Torch v2.2.1 (CUDA 12.1)", "cu121"),
    ("Torch v2.2.2 (CUDA 12.1)", "cu121"),
    ("Torch v2.3.0 (CUDA 12.1)", "cu121"),
    ("Torch v2.3.1 (CUDA 12.1)", "cu121"),
    ("Torch v2.4.0 (CUDA 12.1)", "cu121"),
    ("Torch v2.4.1 (CUDA 12.1)", "cu121"),
    ("Torch v2.5.0 (CUDA 12.1)", "cu121"),
    ("Torch v2.5.1 (CUDA 12.1)", "cu121"),
    # cu124
    ("Torch v2.4.0 (CUDA 12.4)", "cu124"),
    ("Torch v2.4.1 (CUDA 12.4)", "cu124"),
    ("Torch v2.5.0 (CUDA 12.4)", "cu124"),
    ("Torch v2.5.1 (CUDA 12.4)", "cu124"),
    ("Torch v2.6.0 (CUDA 12.4)", "cu124"),
    # cu126
    ("Torch v2.6.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.7.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.7.1 (CUDA 12.6)", "cu126"),
    ("Torch v2.8.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.9.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.9.1 (CUDA 12.6)", "cu126"),
    ("Torch v2.10.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.11.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.12.0 (CUDA 12.6)", "cu126"),
    ("Torch v2.12.1 (CUDA 12.6)", "cu126"),
    ("Torch v2.13.0 (CUDA 12.6)", "cu126"),
    # cu128（官方索引实际只发布到 2.10.0）
    ("Torch v2.7.0 (CUDA 12.8)", "cu128"),
    ("Torch v2.7.1 (CUDA 12.8)", "cu128"),
    ("Torch v2.8.0 (CUDA 12.8)", "cu128"),
    ("Torch v2.9.0 (CUDA 12.8)", "cu128"),
    ("Torch v2.9.1 (CUDA 12.8)", "cu128"),
    ("Torch v2.10.0 (CUDA 12.8)", "cu128"),
    # cu130
    ("Torch v2.9.0 (CUDA 13.0)", "cu130"),
    ("Torch v2.9.1 (CUDA 13.0)", "cu130"),
    ("Torch v2.10.0 (CUDA 13.0)", "cu130"),
    ("Torch v2.11.0 (CUDA 13.0)", "cu130"),
    ("Torch v2.12.0 (CUDA 13.0)", "cu130"),
    ("Torch v2.12.1 (CUDA 13.0)", "cu130"),
    ("Torch v2.13.0 (CUDA 13.0)", "cu130"),
    # cu132（需驱动 CUDA ≥ 13.2）
    ("Torch v2.12.0 (CUDA 13.2)", "cu132"),
    ("Torch v2.12.1 (CUDA 13.2)", "cu132"),
    ("Torch v2.13.0 (CUDA 13.2)", "cu132"),
]


def _commit_date(comfyui_path):
    """HEAD 提交日期，格式 YYYY-MM-DD HH:MM；失败返回空串。"""
    try:
        from .git_utils import run_git
        p = run_git(comfyui_path, "log", "-1", "--format=%cd",
                    "--date=format:%Y-%m-%d %H:%M", check=False)
        return p.stdout.strip()
    except Exception:
        return ""


def _pip_show(python, package):
    """pip show 某包：返回 (已安装, 版本号)。
    版本为 "None"（损坏的 dist-info 残留）视为未安装。"""
    rc, out, _ = _run_full(python, ["-m", "pip", "show", package], timeout=30)
    if rc != 0 or not (out or "").strip():
        return False, ""
    m = re.search(r"(?m)^Version:\s*(\S+)", out)
    ver = m.group(1) if m else ""
    if not ver or ver == "None":
        return False, ""
    return True, ver


def detect_environment(inst, progress=None):
    """识别当前实例环境，返回 dict：
    gpu / python / comfyui / torch / xformers / sageattention / triton / llama_cpp。
    每项为字符串（失败或未安装时给出提示）。"""
    python = inst.resolve_python("python")
    result = {
        "gpu": "未检测到 NVIDIA 显卡",
        "python": "未知",
        "comfyui": "未知",
        "torch": "未知",
        "xformers": "未安装",
        "sageattention": "未安装",
        "triton": "未安装",
        "llama_cpp": "未安装",
    }

    # 显卡：nvidia-smi 列表，多卡逐行列出
    if progress:
        progress("识别显卡…")
    gpus = system_info.gpu_info()
    if gpus:
        result["gpu"] = "\n".join(
            f"GPU {i}: {g['name']}"
            for i, g in enumerate(gpus))

    # Python 版本
    if progress:
        progress("识别 Python 版本…")
    code, line, _ = _run(python, ["--version"])
    if code == 0 and line:
        result["python"] = "Python " + line.replace("Python ", "").strip()

    # ComfyUI 版本（git 标签 + 短提交 + 提交日期；非 git 用 pyproject 版本）
    if progress:
        progress("识别 ComfyUI 版本…")
    try:
        vi = inst.version_info()
        if vi.get("is_git"):
            tag = vi.get("describe") or ""
            commit = vi.get("commit") or ""
            date = _commit_date(inst.path)
            if tag and commit:
                result["comfyui"] = f"{tag} ({commit}) [{date}]" if date \
                    else f"{tag} ({commit})"
            elif commit:
                result["comfyui"] = f"{commit} [{date}]" if date else commit
            else:
                result["comfyui"] = "git 安装"
        elif vi.get("describe"):
            result["comfyui"] = vi.get("describe")
        else:
            result["comfyui"] = "非 git 安装"
    except Exception:
        result["comfyui"] = "未知"

    # torch / xformers / sageattention / triton / llama-cpp 版本
    if progress:
        progress("识别 torch 版本…")
    tbase, tcu = _installed_torch(python)
    if tbase:
        result["torch"] = f"torch=={tbase}+{tcu}" if tcu else f"torch=={tbase}"
    else:
        result["torch"] = "torch: 未安装"
    if progress:
        progress("识别 xformers 版本…")
    ok, ver = _pip_show(python, "xformers")
    result["xformers"] = f"xformers=={ver}" if ok else "xformers: 未安装"
    if progress:
        progress("识别 sageattention 版本…")
    ok, ver = _pip_show(python, "sageattention")
    result["sageattention"] = f"sageattention=={ver}" if ok else "sageattention: 未安装"
    if progress:
        progress("识别 triton 版本…")
    for pkg in ("triton-windows", "triton"):
        ok, ver = _pip_show(python, pkg)
        if ok:
            result["triton"] = f"{pkg}=={ver}"
            break
    if progress:
        progress("识别 llama-cpp 版本…")
    ok, ver = _pip_show(python, "llama-cpp-python")
    result["llama_cpp"] = f"llama-cpp-python=={ver}" if ok \
        else "llama-cpp-python: 未安装"
    return result
