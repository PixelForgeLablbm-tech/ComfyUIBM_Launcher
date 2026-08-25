# -*- coding: utf-8 -*-
"""后台任务线程封装：避免阻塞 UI。"""
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


class TaskManager:
    """持有所有运行中的线程引用，避免被 GC 回收。"""

    def __init__(self):
        self._threads = []

    def start(self, fn, *args, on_done=None, on_error=None, on_progress=None):
        thread = TaskThread(fn, *args)
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
        if thread in self._threads:
            self._threads.remove(thread)

    def active_count(self) -> int:
        return len(self._threads)
