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
from .system_info import clean_log_chunk, port_open

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
LOG_CAP = 3000


class RunningInfo:
    """运行中的进程信息。"""

    def __init__(self, pid, instance_id, instance_name, port, url, started_at):
        self.pid = pid
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.port = port
        self.url = url
        self.started_at = started_at

    def to_dict(self):
        return {
            "pid": self.pid,
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "port": self.port,
            "url": self.url,
            "started_at": self.started_at,
            "uptime_secs": 0,
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
    def launch(self, inst, launch: dict, mirrors: dict) -> dict:
        port = int(launch.get("port", 8188))
        if port_open(port):
            raise RuntimeError(
                f"端口 {port} 已被占用，可能已有 ComfyUI 在运行。\n"
                "请先停止旧进程，或更换端口。")
        with self._lock:
            if self._info:
                self.stop()

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
            if child is not None and child.poll() is not None:
                code = child.returncode
                with self._lock:
                    self._child = None
                    was_manual = self._manual_stop
                    auto_restart = self._auto_restart
                    self._info = None
                    self._ready_fired = False
                    last = self._last_launch
                self.append_log(f"[启动器] 进程已退出，退出码 {code}")
                self.log_line.emit(f"[启动器] 进程已退出，退出码 {code}")
                self.running_changed.emit(None)
                self.exited.emit(code)
                if not was_manual and auto_restart and last:
                    self.append_log("[启动器] 检测到异常退出，2 秒后自动重启…")
                    self.log_line.emit("[启动器] 检测到异常退出，2 秒后自动重启…")
                    time.sleep(2)
                    try:
                        inst, launch, mirrors = last
                        self.launch(inst, launch, mirrors)
                    except Exception as e:
                        self.append_log(f"[启动器] 自动重启失败：{e}")
                        self.log_line.emit(f"[启动器] 自动重启失败：{e}")
            else:
                # 端口就绪兜底：日志没匹配到就绪行时，端口通了也通知
                with self._lock:
                    ready = self._ready_fired
                    info = self._info
                if info and not ready and port_open(info.port):
                    self._fire_ready(None)
            time.sleep(0.5)

    # ---------------- 停止 ----------------
    def stop(self):
        with self._lock:
            self._manual_stop = True
            self._auto_restart = False
            child = self._child
            self._child = None
            self._info = None
            self._ready_fired = False
        if child is not None and child.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                try:
                    child.terminate()
                    child.wait(timeout=10)
                except Exception:
                    child.kill()
        self.append_log("[启动器] 已停止。")
        self.log_line.emit("[启动器] 已停止。")
        self.running_changed.emit(None)

    def shutdown(self):
        """退出时调用：停止自动重启并停止监控线程。"""
        with self._lock:
            self._auto_restart = False
            self._manual_stop = True
        self._monitor_stop.set()
