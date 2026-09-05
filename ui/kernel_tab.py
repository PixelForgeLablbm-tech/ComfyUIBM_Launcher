# -*- coding: utf-8 -*-
"""内核维护页签：环境识别（左）+ 内核组件安装（右）。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from launcher import kernel_manager
from ui.dialogs import TorchInstallDialog, VersionInstallDialog, WheelInstallDialog


class KernelTab(QWidget):
    """内核维护：识别环境 / 安装 Torch、xformers、Triton、llama-cpp、SageAttention。"""

    # (显示名, 安装规格/说明, 右侧说明)
    ITEMS = [
        ("Torch", "torch torchvision torchaudio", "深度学习框架"),
        ("xformers", "按已装 torch 自动匹配官方 Windows 轮子", "注意力优化"),
        ("Triton", "-U triton-windows<3.8", "GPU 编译内核"),
        ("llama-cpp", "JamePeng CUDA 版轮子（按 CUDA/Python 匹配）", "LLM 本地推理"),
        ("SageAttention", "官方 Releases 轮子（按 torch/CUDA 匹配）", "高效注意力实现"),
    ]

    # 可卸载组件 → pip 包名（Torch 不加卸载，避免误卸破坏环境）
    UNINSTALL_NAMES = {
        "xformers": ["xformers"],
        "Triton": ["triton-windows"],
        "llama-cpp": ["llama-cpp-python"],
        "SageAttention": ["sageattention"],
    }

    # 组件 → 环境识别结果里的键（识别后中间列显示对应已装版本）
    ENV_KEYS = {
        "Torch": "torch",
        "xformers": "xformers",
        "Triton": "triton",
        "llama-cpp": "llama_cpp",
        "SageAttention": "sageattention",
    }

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._rows = {}
        self._un_buttons = {}
        self._version_labels = {}      # 组件名 → 版本显示 QLabel
        self._busy = False
        self._detected_uid = None     # 已成功识别环境的实例 uid
        self._pending_uid = None
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(12)

        # 上：内核组件安装（整行）
        card = QGroupBox("内核组件安装（当前实例的 Python 环境）")
        v = QVBoxLayout(card)
        v.setSpacing(8)
        hint_row = QHBoxLayout()
        self.lb_hint = QLabel("请先在「实例管理」中选择一个本地实例。")
        self.lb_hint.setProperty("dim", True)
        hint_row.addWidget(self.lb_hint, 1)
        self.btn_detect = QPushButton("识别环境")
        self.btn_detect.setObjectName("ghost")
        self.btn_detect.setFixedHeight(30)
        self.btn_detect.clicked.connect(self.detect)
        hint_row.addWidget(self.btn_detect)
        v.addLayout(hint_row)
        for name, spec, desc in self.ITEMS:
            row = QHBoxLayout()
            row.setSpacing(10)
            btn = QPushButton(f"安装 {name}")
            btn.setObjectName("primary")
            btn.setFixedHeight(34)
            btn.setMinimumWidth(140)
            btn.setToolTip(spec)      # 规格信息悬停可见
            if name in self.UNINSTALL_NAMES:
                btn_un = QPushButton("卸载")
                btn_un.setObjectName("ghost")
                btn_un.setFixedHeight(30)
                btn_un.setMinimumWidth(60)
                btn_un.clicked.connect(
                    lambda _=False, n=name: self._uninstall(n))
            else:
                btn_un = None
            if name == "Torch":
                btn.clicked.connect(
                    lambda _=False: self._install_torch_dialog())
            elif name == "xformers":
                btn.clicked.connect(
                    lambda _=False: self._install_kernel_wheel(
                        "xformers", "xformers"))
            elif name == "SageAttention":
                btn.clicked.connect(
                    lambda _=False: self._install_kernel_wheel(
                        "SageAttention", "sageattention"))
            elif name == "llama-cpp":
                btn.clicked.connect(
                    lambda _=False: self._install_kernel_wheel(
                        "llama-cpp", "llamacpp"))
            elif name == "Triton":
                btn.clicked.connect(
                    lambda _=False: self._install_triton())
            ver_lb = QLabel("")
            ver_lb.setAlignment(Qt.AlignLeft)
            desc_lb = QLabel(desc)
            desc_lb.setProperty("dim", True)
            desc_lb.setAlignment(Qt.AlignCenter)   # 居中
            desc_lb.setFixedWidth(110)             # 固定在最右侧一列
            row.addWidget(btn)
            if btn_un:
                row.addWidget(btn_un)
            row.addWidget(ver_lb, 1)               # 中间：版本显示（识别后填充）
            row.addWidget(desc_lb)                 # 不加伸缩 → 固定在右端
            v.addLayout(row)
            self._rows[name] = btn
            self._un_buttons[name] = btn_un
            self._version_labels[name] = ver_lb
        lay.addWidget(card)

        # 下：左 环境识别 / 右 安装日志
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        env_card = QGroupBox("环境识别")
        ev = QVBoxLayout(env_card)
        ev.setSpacing(10)
        self.lb_env = QPlainTextEdit()
        self.lb_env.setReadOnly(True)
        self.lb_env.setMaximumBlockCount(500)
        self.lb_env.setPlaceholderText("点击上方「识别环境」识别当前环境")
        ev.addWidget(self.lb_env, 1)
        bottom.addWidget(env_card, 1)

        log_card = QGroupBox("安装日志")
        lv2 = QVBoxLayout(log_card)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setPlaceholderText("点击上方按钮开始安装，这里显示进度与结果。")
        lv2.addWidget(self.log)
        bottom.addWidget(log_card, 1)

        lay.addLayout(bottom, 1)

    # ------------------------------------------------------------ 数据
    def _clear_versions(self):
        """清空中间版本列（未识别/换实例/重新识别时）。"""
        for lb in self._version_labels.values():
            lb.setText("")

    def reload(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            self.lb_hint.setText("请先在「实例管理」中选择一个本地实例。")
            self.btn_detect.setEnabled(False)
            for btn in self._rows.values():
                btn.setEnabled(False)
            self._clear_versions()
            return
        text = f"实例：{inst.name}　{inst.path}"
        self.lb_hint.setText(text)
        self.lb_hint.setToolTip(text)      # 完整路径悬停可见
        self.lb_hint.setWordWrap(False)    # 单行不换行
        self.btn_detect.setEnabled(True)
        for btn in self._rows.values():
            btn.setEnabled(True)
        # 换实例后需重新识别才显示版本
        if self._detected_uid != inst.uid:
            self._clear_versions()

    def detect(self):
        """后台识别环境并显示到左侧面板。"""
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(self, "提示", "请先在「实例管理」中选择一个本地实例")
            return
        self.btn_detect.setEnabled(False)
        self.btn_detect.setText("识别中…")
        self.lb_env.setPlainText("识别中…")
        self._pending_uid = inst.uid
        self._clear_versions()          # 重新识别期间版本列清空

        self.win.tasks.start(
            lambda report, i=inst: kernel_manager.detect_environment(i, report),
            on_progress=self._show_progress,
            on_done=self._show_env,
            on_error=self._detect_error,
        )

    def _show_progress(self, msg):
        self.lb_env.setPlainText(msg)

    def _show_env(self, env):
        self.btn_detect.setEnabled(True)
        self.btn_detect.setText("重新识别")
        self._detected_uid = self._pending_uid
        lines = [
            "获取当前显卡型号:",
            env["gpu"],
            "",
            "获取当前Python版本:",
            env["python"],
            "",
            "当前ComfyUI版本:",
            env["comfyui"],
            "",
            "获取当前torch版本:",
            env["torch"],
            "",
            "获取当前xformers版本:",
            env["xformers"],
            "",
            "获取当前sageattention版本:",
            env["sageattention"],
            "",
            "获取当前triton-windows版本:",
            env["triton"],
            "",
            "获取当前llama-cpp版本:",
            env["llama_cpp"],
        ]
        self.lb_env.setPlainText("\n".join(lines))
        # 中间列显示各组件已装版本（识别后）
        for name, lb in self._version_labels.items():
            key = self.ENV_KEYS.get(name)
            if key and key in env:
                lb.setText(f"<span style='color:#8b96a8'>{env[key]}</span>")
        self._detected_uid = self._pending_uid
        self.win.log("环境识别完成")

    def _detect_error(self, err):
        self.btn_detect.setEnabled(True)
        self.btn_detect.setText("重新识别")
        self.lb_env.setPlainText(f"识别失败：{err}")

    # ------------------------------------------------------------ 安装
    def _install_torch_dialog(self):
        """安装 Torch：先弹窗选版本（检测驱动/CUDA），确认后安装。"""
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(self, "提示", "请先在「实例管理」中选择一个本地实例")
            return
        if self.win.pm.is_running():
            QMessageBox.warning(self, "提示", "请先停止正在运行的 ComfyUI 再安装 Torch")
            return
        driver, cuda = kernel_manager.detect_cuda()
        dlg = TorchInstallDialog(driver, cuda, parent=self)
        if dlg.exec_() != dlg.Accepted or not dlg.result:
            return
        label = dlg.result["label"]
        suffix = dlg.result["suffix"]
        version = dlg.result.get("version", "")
        ret = QMessageBox.question(
            self, "确认安装",
            f"即将安装 {label}\n"
            f"将从 PyTorch 官方源下载（约 2GB），并替换当前 torch。\n\n"
            f"请确保磁盘空间充足（≥5GB），期间请勿关闭程序。\n\n"
            "确定开始安装吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self._set_busy(True)
        self.log.clear()
        mirrors = dict(self.win.config.mirrors)

        def work(report):
            kernel_manager.install_torch(inst, suffix, mirrors, report,
                                         version=version)
            return f"Torch 安装完成：{label}"

        self.win.tasks.start(
            work,
            on_progress=self._append_log,
            on_done=lambda msg: self._done(msg),
            on_error=self._error,
        )

    def _install_kernel_wheel(self, name, which):
        """xformers / SageAttention / llama-cpp：先弹窗选轮子（自动预选匹配项），
        确认后再事务式安装所选轮子。"""
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(self, "提示", "请先在「实例管理」中选择一个本地实例")
            return
        if self.win.pm.is_running():
            QMessageBox.warning(self, "提示", "请先停止正在运行的 ComfyUI 再安装内核组件")
            return
        self._set_busy(True)
        self.log.clear()
        install_func = {
            "xformers": kernel_manager.install_xformers,
            "sageattention": kernel_manager.install_sageattention,
            "llamacpp": kernel_manager.install_llamacpp,
        }[which]

        # 阶段 1：后台获取可用轮子列表（含自动预选下标）
        def fetch(report):
            report(f"⏳ 正在获取 {name} 可用轮子列表…")
            return kernel_manager.wheel_install_plan(inst, which)

        def pick(plan):
            self._set_busy(False)
            if not plan.get("items"):
                QMessageBox.information(
                    self, "提示",
                    "没有获取到可用轮子（网络异常或没有匹配项），请稍后重试")
                return
            dlg = WheelInstallDialog(plan, parent=self)
            if dlg.exec_() != dlg.Accepted or not dlg.result:
                return
            url = dlg.result["url"]
            self._set_busy(True)
            self.log.clear()
            mirrors = dict(self.win.config.mirrors)

            # 阶段 2：安装用户选择的轮子（事务式：预检/验证/失败回滚）
            def work(report):
                install_func(inst, mirrors, report, url=url)
                return f"安装完成：{name}"

            self.win.tasks.start(
                work,
                on_progress=self._append_log,
                on_done=lambda msg: self._done(msg),
                on_error=self._error,
            )

        self.win.tasks.start(
            fetch,
            on_progress=self._append_log,
            on_done=pick,
            on_error=self._error,
        )

    def _install_triton(self):
        """Triton：先弹窗选版本（自动预选最新 <3.8），确认后安装所选版本。"""
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(self, "提示", "请先在「实例管理」中选择一个本地实例")
            return
        if self.win.pm.is_running():
            QMessageBox.warning(self, "提示", "请先停止正在运行的 ComfyUI 再安装内核组件")
            return
        self._set_busy(True)
        self.log.clear()

        def fetch(report):
            report("⏳ 正在获取 triton-windows 可用版本…")
            return kernel_manager.triton_plan(inst)

        def pick(plan):
            self._set_busy(False)
            if not plan.get("items"):
                QMessageBox.information(
                    self, "提示", "没有获取到可用版本（网络异常），请稍后重试")
                return
            dlg = VersionInstallDialog(plan, parent=self)
            if dlg.exec_() != dlg.Accepted or not dlg.result:
                return
            version = dlg.result["value"]
            self._set_busy(True)
            self.log.clear()
            mirrors = dict(self.win.config.mirrors)

            def work(report):
                kernel_manager.install_package(
                    inst, f"triton-windows=={version}", mirrors, report)
                return f"安装完成：Triton {version}"

            self.win.tasks.start(
                work,
                on_progress=self._append_log,
                on_done=lambda msg: self._done(msg),
                on_error=self._error,
            )

        self.win.tasks.start(
            fetch,
            on_progress=self._append_log,
            on_done=pick,
            on_error=self._error,
        )

    def _append_log(self, msg):
        self.log.appendPlainText(msg)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_busy(self, busy):
        self._busy = busy
        for btn in self._rows.values():
            btn.setEnabled(not busy)
        for btn in self._un_buttons.values():
            if btn:
                btn.setEnabled(not busy)

    def _uninstall(self, name):
        """卸载内核组件（Torch 除外）：确认后 pip uninstall。"""
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(self, "提示", "请先在「实例管理」中选择一个本地实例")
            return
        if self.win.pm.is_running():
            QMessageBox.warning(self, "提示", "请先停止正在运行的 ComfyUI 再卸载内核组件")
            return
        names = self.UNINSTALL_NAMES.get(name)
        if not names:
            return
        ret = QMessageBox.question(
            self, "确认卸载",
            f"确定卸载 {name}（{' '.join(names)}）？\n\n"
            "卸载后相关功能将不可用；如需要可随时重新安装。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self._set_busy(True)
        self.log.clear()
        mirrors = dict(self.win.config.mirrors)

        def work(report):
            kernel_manager.uninstall_package(inst, names, mirrors, report)
            return f"卸载完成：{name}"

        self.win.tasks.start(
            work,
            on_progress=self._append_log,
            on_done=lambda msg: self._done(msg),
            on_error=self._error,
        )

    def _done(self, msg):
        self._set_busy(False)
        self._append_log(f"════════ ✅ {msg} ════════")
        QMessageBox.information(self, "完成", msg)
        self.win.log(msg)

    def _error(self, err):
        self._set_busy(False)
        self._append_log(f"════════ ❌ 失败 ════════\n{err}")
        QMessageBox.critical(self, "安装失败", str(err))
        self.win.log(f"内核安装失败: {err}")
