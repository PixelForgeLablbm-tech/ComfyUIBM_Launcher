# -*- coding: utf-8 -*-
"""ComfyUI 进程管理：启动/停止、实时日志、就绪检测、自动重启、监控线程。"""
import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from . import git_utils  # noqa: F401  保持 import 链完整
from .args import build_args, filter_unsupported, probe_supported_args
from .mirrors import git_extra_and_env
from .system_info import (
    clean_log_chunk, cmdline_snapshot, port_open, port_owner_pids,
    process_cmdline,
)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
LOG_CAP = 3000
# 子进程消失后等待「被网页/外部重启的进程接管」的时间窗口（秒）
TAKEOVER_WINDOW = 2.5


class RunningInfo:
    """运行中的进程信息。

    adopted=True 表示该进程不是本启动器 spawn 的，而是启动后
    被网页/外部重启、由启动器按端口/命令行「接管」识别的进程。
    """

    def __init__(self, pid, instance_id, instance_name, port, url,
                 started_at, adopted=False):
        self.pid = pid
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.port = port
        self.url = url
        self.started_at = started_at
        self.adopted = adopted

    def to_dict(self):
        return {
            "pid": self.pid,
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "port": self.port,
            "url": self.url,
            "started_at": self.started_at,
            "uptime_secs": 0,
            "adopted": self.adopted,
        }


# ---------------------------------------------------------------- 参数适配
def _probe_and_filter(python, comfy_dir, args):
    """版本参数适配：不支持的参数自动忽略，返回过滤后的参数。"""
    supported = probe_supported_args(python, comfy_dir)
    if not supported:
        return args, []
    return filter_unsupported(args, supported)


# ---------------------------------------------------------------- 进程管理
class ProcessManager(QObject):
    log_line = pyqtSignal(str)        # 实时日志行
    ready = pyqtSignal(str)           # ComfyUI 就绪 URL
    exited = pyqtSignal(int)          # 进程退出码
    running_changed = pyqtSignal(object)  # RunningInfo 或 None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.RLock()
        self._child = None
        self._info = None
        self._started = 0.0
        self._auto_restart = False
        self._manual_stop = False
        self._auto_browser = True
        self._ready_fired = False
        self._adopted = False       # 当前运行进程是否是被接管(网页/外部重启)的
        self._resolving = False     # 是否正在做「接管检测」，防止重入
        self._last_launch = None
        self._log_buffer = []
        self._monitor_stop = threading.Event()
        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor.start()

    # ---------------- 日志 ----------------
    def append_log(self, line: str):
        if not line:
            return
        with self._lock:
            self._log_buffer.append(line)
            if len(self._log_buffer) > LOG_CAP:
                del self._log_buffer[: len(self._log_buffer) - LOG_CAP]

    def full_log(self):
        with self._lock:
            return list(self._log_buffer)

    def clear_log(self):
        with self._lock:
            self._log_buffer.clear()

    # ---------------- 状态 ----------------
    def running_info(self):
        with self._lock:
            if not self._info:
                return None
            d = self._info.to_dict()
            d["uptime_secs"] = int(time.time() - self._started)
            return d

    def is_running(self) -> bool:
        with self._lock:
            return self._info is not None

    # ---------------- 参数构建 ----------------
    def build_args(self, launch: dict, inst) -> list:
        return build_args(launch, inst.launch_args)

    # ---------------- 启动 ----------------
    def port_blocker(self, inst, launch: dict, exclude=()) -> int:
        """期望端口被占用时返回占用者 PID，未被占用返回 0。

        已在本启动器当前子进程手里（或在 exclude 集合里，通常是刚停掉的
        自己）不算占用。界面据此弹窗「结束占用并继续启动」。
        """
        port = int(launch.get("port", 8188))
        if not port_open(port):
            return 0
        with self._lock:
            own = self._child.pid if self._child is not None else None
        for pid in port_owner_pids(port):
            if pid == own or pid in exclude:
                continue
            return pid
        return 0

    def kill_pid_tree(self, pid: int):
        """结束一个进程及其进程树（Windows taskkill /T /F）。"""
        if not pid:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True,
                           creationflags=CREATE_NO_WINDOW)
        else:
            try:
                os.kill(pid, 9)
            except Exception:
                pass

    def launch(self, inst, launch: dict, mirrors: dict) -> dict:
        port = int(launch.get("port", 8188))
        with self._lock:
            old = self._child.pid if self._child is not None else None
            if self._info:
                self.stop()
        # 若我们自己占着端口，上面已停掉；这里只拦「外部进程占用」
        # （刚停掉的旧 PID 可能还残留在 netstat 里，需排除并稍等它释放）
        blocker = self.port_blocker(inst, launch,
                                    exclude=((old,) if old else ()))
        for _ in range(3):
            if not blocker:
                break
            time.sleep(0.3)
            blocker = self.port_blocker(inst, launch,
                                        exclude=((old,) if old else ()))
        if blocker:
            raise RuntimeError(
                f"端口 {port} 正被 PID {blocker} 占用（非本启动器启动）。\n"
                "请先停止该进程，或更换端口。")

        python = inst.resolve_python("") or "python"
        if not Path(python).exists() and python == "python":
            # 允许 PATH 中的 python
            pass
        main = Path(inst.path) / "main.py"
        if not main.exists():
            raise RuntimeError(f"未找到 main.py：{main}")

        args = self.build_args(launch, inst)
        # 版本参数适配：不支持的参数自动忽略
        args, dropped = _probe_and_filter(python, Path(inst.path), args)
        if dropped:
            self.append_log(f"[启动器] 以下参数当前版本不支持，已自动忽略："
                            f"{' '.join(dropped)}")
            self.log_line.emit(f"[启动器] 以下参数当前版本不支持，已自动忽略："
                               f"{' '.join(dropped)}")

        cmd = [python, str(main)] + args
        env = dict(os.environ)
        env["PYTHONPATH"] = inst.path
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        pdir = str(Path(python).parent)
        env["PATH"] = pdir + os.pathsep + env.get("PATH", "")
        if mirrors.get("hf_mirror"):
            env["HF_ENDPOINT"] = "https://hf-mirror.com"
        _extra, penv = git_extra_and_env(mirrors)
        env.update(penv)

        try:
            child = subprocess.Popen(
                cmd, cwd=inst.path, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
            )
        except FileNotFoundError:
            raise RuntimeError(f"找不到 Python：{python}\n"
                               "请在实例或全局设置中指定正确的 Python 路径。")
        except Exception as e:
            raise RuntimeError(f"启动失败：{e}")

        url = f"http://127.0.0.1:{port}"
        info = RunningInfo(
            pid=child.pid, instance_id=inst.uid,
            instance_name=inst.name, port=port, url=url,
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        with self._lock:
            self._child = child
            self._info = info
            self._started = time.time()
            self._auto_restart = bool(launch.get("auto_restart", True))
            self._manual_stop = False
            self._auto_browser = bool(launch.get("auto_launch_browser", True))
            self._ready_fired = False
            self._adopted = False
            self._resolving = False
            self._last_launch = (inst, dict(launch), dict(mirrors))

        self.append_log(f"[启动器] 已启动 (PID {child.pid})，监听 {url}，实时日志如下：")
        self.log_line.emit(f"[启动器] 已启动 (PID {child.pid})，监听 {url}")
        threading.Thread(target=self._read_stream, args=(child.stdout,),
                         daemon=True).start()
        threading.Thread(target=self._read_stream, args=(child.stderr,),
                         daemon=True).start()
        self.running_changed.emit(self.running_info())
        return self.running_info()

    def _read_stream(self, stream):
        try:
            for raw in iter(stream.readline, b""):
                line = raw.decode("utf-8", errors="replace")
                for piece in clean_log_chunk(line):
                    self.append_log(piece)
                    self.log_line.emit(piece)
                    if "To see the GUI go to" in piece:
                        url = next((t for t in piece.split()
                                    if t.startswith("http")), None)
                        self._fire_ready(url)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _fire_ready(self, url=None):
        with self._lock:
            if self._ready_fired:
                return
            self._ready_fired = True
            auto_browser = self._auto_browser
            info = self._info
        if not url and info:
            url = info.url
        if url:
            self.ready.emit(url)
            if auto_browser:
                try:
                    webbrowser.open(url)
                except Exception:
                    pass

    def _monitor_loop(self):
        while not self._monitor_stop.is_set():
            with self._lock:
                child = self._child
                info = self._info
                adopted = self._adopted
                resolving = self._resolving
            if child is not None and child.poll() is not None:
                self._handle_child_exit(child.returncode)
                continue
            if info is not None and not resolving and adopted:
                # 接管来的进程也消失了：可能又被网页重启，也可能已停止
                if not port_open(info.port):
                    self._handle_running_lost()
                    continue
            # 端口就绪兜底：日志没匹配到就绪行时，端口通了也通知
            if info is not None and not self._ready_fired and port_open(info.port):
                self._fire_ready(None)
            time.sleep(0.5)

    # ---------------- 退出处理 / 接管检测 ----------------
    @staticmethod
    def _cmd_matches(cmd: str, inst) -> bool:
        """命令行是否属于该实例的 ComfyUI（用该实例目录下的 python 跑 main.py）。"""
        if not cmd:
            return False
        low = cmd.lower().replace("/", "\\")
        base = str(Path(inst.path)).lower().replace("/", "\\")
        return "main.py" in low and base in low

    def _wait_takeover(self, inst, port, exclude=()):
        """子进程消失后，等待被网页/外部重启的进程接管。

        返回：>0 接管进程 PID；-1 端口被其他程序占用；None 无人接管。
        """
        deadline = time.time() + TAKEOVER_WINDOW
        last_snap = 0.0
        me = os.getpid()
        while time.time() < deadline:
            if port_open(port):
                for pid in port_owner_pids(port):
                    if pid in exclude or pid == me:
                        continue
                    if self._cmd_matches(process_cmdline(pid), inst):
                        return pid
                return -1            # 端口被非本实例的进程占用
            now = time.time()
            if now - last_snap >= 0.6:
                last_snap = now
                snap = cmdline_snapshot()
                # 命令行含本实例 main.py 的新进程 → 立即接管（端口可能还没就绪）
                for pid, cmd in snap.items():
                    if pid in exclude or pid == me:
                        continue
                    if self._cmd_matches(cmd, inst):
                        return pid
            time.sleep(0.3)
        return None

    def _adopt(self, pid, inst, launch, mirrors, port):
        """接管一个不是本启动器拉起的 ComfyUI 进程，继续监控与提供停止。"""
        info = RunningInfo(
            pid=pid, instance_id=inst.uid, instance_name=inst.name,
            port=port, url=f"http://127.0.0.1:{port}",
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"), adopted=True,
        )
        with self._lock:
            self._child = None
            self._info = info
            self._started = time.time()
            self._auto_restart = bool(launch.get("auto_restart", True))
            self._manual_stop = False
            self._auto_browser = False    # 网页重启：浏览器已在，不重复打开
            self._ready_fired = False
            self._adopted = True
            self._resolving = False
            self._last_launch = (inst, dict(launch), dict(mirrors))
        self.append_log(f"[启动器] 检测到 ComfyUI 已被重新启动 (PID {pid})，"
                        f"已接管并继续监控。")
        self.log_line.emit(f"[启动器] 检测到 ComfyUI 已被重新启动 (PID {pid})，"
                           f"已接管并继续监控。")
        self.running_changed.emit(self.running_info())

    def _resolve_takeover(self, last, port, code=None, exclude=()):
        """进程消失后的统一处理：等接管 → 接管 / 停止 / 按需自动重启。"""
        with self._lock:
            if self._resolving:
                return
            self._resolving = True
        try:
            inst, launch, mirrors = last
            with self._lock:
                if self._manual_stop:
                    self._clear_running(code)
                    return
                auto = self._auto_restart
            pid = self._wait_takeover(inst, port, exclude=exclude)
            with self._lock:
                if self._manual_stop:
                    # 等待期间用户点了停止：把新拉起的进程也一并结束
                    if pid and pid > 0:
                        self.kill_pid_tree(pid)
                    self._clear_running(code)
                    return
            if pid and pid > 0:
                self._adopt(pid, inst, launch, mirrors, port)
                return
            if pid == -1:
                self.append_log("[启动器] 端口已被其他程序占用，不再接管/自动重启。")
                self.log_line.emit("[启动器] 端口已被其他程序占用，不再接管/自动重启。")
            else:
                self.append_log("[启动器] 未检测到接管进程，视为已停止。")
                self.log_line.emit("[启动器] 未检测到接管进程，视为已停止。")
            self._clear_running(code)
            if pid is None and auto:
                self.append_log("[启动器] 检测到异常退出，自动重启…")
                self.log_line.emit("[启动器] 检测到异常退出，自动重启…")
                try:
                    self.launch(inst, launch, mirrors)
                except Exception as e:
                    self.append_log(f"[启动器] 自动重启失败：{e}")
                    self.log_line.emit(f"[启动器] 自动重启失败：{e}")
        finally:
            with self._lock:
                self._resolving = False

    def _clear_running(self, code=None):
        """清空运行状态并广播停止；code 非 None 时补发 exited 信号。"""
        with self._lock:
            self._info = None
            self._ready_fired = False
            self._adopted = False
        self.running_changed.emit(None)
        if code is not None:
            self.exited.emit(code)

    def _handle_child_exit(self, code):
        with self._lock:
            child_pid = self._child.pid if self._child is not None else None
            self._child = None
            was_manual = self._manual_stop
            info = self._info
            self._ready_fired = False
        self.append_log(f"[启动器] 进程已退出，退出码 {code}")
        self.log_line.emit(f"[启动器] 进程已退出，退出码 {code}")
        if was_manual or info is None or not self._last_launch:
            self._clear_running(code)
            return
        self._resolve_takeover(self._last_launch, info.port, code=code,
                               exclude=(child_pid,) if child_pid else ())

    def _handle_running_lost(self):
        with self._lock:
            if self._info is None or not self._adopted or self._resolving:
                return
            port = self._info.port
            last = self._last_launch
            self._ready_fired = False
        self.append_log("[启动器] 检测到 ComfyUI 停止或被再次重启，等待接管…")
        self.log_line.emit("[启动器] 检测到 ComfyUI 停止或被再次重启，等待接管…")
        if not last:
            self._clear_running()
            return
        self._resolve_takeover(last, port, code=None)

    # ---------------- 停止 ----------------
    def stop(self, ask_foreign=None):
        """停止当前 ComfyUI。

        目标 = 本启动器拉起的子进程树 + 占用该端口的所有进程（可能包含
        被网页/外部重启后接管到的新进程）。其中非本启动器拉起的进程在
        ask_foreign 回调（界面确认）通过后才一并结束；返回 False 表示取消。
        """
        with self._lock:
            child = self._child
            info = self._info
            port = info.port if info else None
        targets = []
        if child is not None and child.poll() is None:
            targets.append(child.pid)
        if port:
            for pid in port_owner_pids(port):
                if pid not in targets:
                    targets.append(pid)
        foreign = [p for p in targets
                   if not (child is not None and p == child.pid)]
        if foreign and ask_foreign is not None:
            if not ask_foreign(list(foreign)):
                return False
        with self._lock:
            self._manual_stop = True
            self._auto_restart = False
            self._child = None
            self._info = None
            self._ready_fired = False
            self._adopted = False
        for pid in targets:
            self.kill_pid_tree(pid)
        self.append_log("[启动器] 已停止。")
        self.log_line.emit("[启动器] 已停止。")
        self.running_changed.emit(None)
        return True

    def shutdown(self):
        """退出时调用：停止自动重启并停止监控线程。"""
        with self._lock:
            self._auto_restart = False
            self._manual_stop = True
        self._monitor_stop.set()
