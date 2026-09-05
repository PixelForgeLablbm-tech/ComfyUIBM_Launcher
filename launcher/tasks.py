# -*- coding: utf-8 -*-
"""后台任务线程封装：避免阻塞 UI。"""
import itertools

from PyQt5.QtCore import QObject, QThread, pyqtSignal


class TaskSignals(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class TaskThread(QThread):
    """在后台线程执行 fn(report, *args)，通过信号回传进度与结果。

    report 是一个可调用对象，用于在线程内向 UI 推送进度文本。
    所有信号发射都做安全保护：应用关闭导致 C++ 信号对象被销毁时
    静默忽略，避免 "wrapped C/C++ object has been deleted" 崩溃。
    """

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self.signals = TaskSignals()

    def run(self):
        try:
            result = self._fn(self._emit_progress, *self._args)
            self._emit(self.signals.finished, result)
        except Exception as e:
            self._emit(self.signals.error, str(e))

    def _emit_progress(self, msg):
        self._emit(self.signals.progress, msg)

    @staticmethod
    def _emit(signal, value):
        try:
            signal.emit(value)
        except RuntimeError:
            pass                      # 应用已退出，信号对象已销毁

    @property
    def progress(self):
        return self.signals.progress

    @property
    def done(self):
        return self.signals.finished

    @property
    def failed(self):
        return self.signals.error


class TaskManager(QObject):
    """持有所有运行中的线程引用，避免被 GC 回收。

    所有任务的开始/进度/结束都会广播到 activity 信号
    (task_id, kind, payload)：kind ∈ {"start", "progress", "end"}。
    供主窗口底部全局进度条等 UI 使用；任务自身的 on_progress 回调不受影响。
    """

    activity = pyqtSignal(int, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._threads = []
        self._warn = {}            # thread -> 关闭前是否需提醒
        self._seq = itertools.count(1)

    def start(self, fn, *args, on_done=None, on_error=None, on_progress=None,
              warn_on_close=True):
        """warn_on_close=False 的任务（状态轮询/版本检查等秒级任务）
        在关闭窗口时不弹"后台任务运行中"提醒。"""
        tid = next(self._seq)
        thread = TaskThread(fn, *args)
        self._warn[thread] = bool(warn_on_close)

        def _started():
            self.activity.emit(tid, "start", None)
        thread.started.connect(_started)

        def _on_p(msg):
            self.activity.emit(tid, "progress", msg)
        thread.progress.connect(_on_p)

        def _ended(_p=None):
            self.activity.emit(tid, "end", None)
        thread.done.connect(_ended)
        thread.failed.connect(_ended)

        if on_progress:
            thread.progress.connect(on_progress)
        if on_done:
            thread.done.connect(on_done)
        if on_error:
            thread.failed.connect(on_error)
        thread.done.connect(lambda _r: self._cleanup(thread))
        thread.failed.connect(lambda _e: self._cleanup(thread))
        self._threads.append(thread)
        thread.start()
        return thread

    def _cleanup(self, thread):
        self._warn.pop(thread, None)
        if thread in self._threads:
            self._threads.remove(thread)

    def active_count(self) -> int:
        return len(self._threads)

    def active_warn_count(self) -> int:
        """运行中且标记为"关闭需提醒"的任务数。"""
        return sum(1 for t in self._threads if self._warn.get(t, True))
