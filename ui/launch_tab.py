# -*- coding: utf-8 -*-
"""启动控制台页签：显存模式/端口/GPU/参数 + 实时日志 + 运行状态。"""
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from launcher import system_info

MODES = [
    ("auto", "自动检测", "由 ComfyUI 自行决定显存策略"),
    ("lowvram", "低显存", "--lowvram 适合 ≤8G 显存"),
    ("normalvram", "标准", "默认行为，不传参（兼容所有版本）"),
    ("highvram", "高显存", "--highvram 适合大显存"),
    ("novram", "无显存限制", "--novram 全部加载到显存"),
    ("cpu", "纯 CPU", "--cpu 无显卡时使用"),
]
ATTENTIONS = [
    ("auto", "自动"),
    ("split", "Split (xformers)"),
    ("pytorch", "PyTorch 原生"),
]


class LaunchTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._build()
        # 实时日志接入
        self.win.pm.log_line.connect(self.append_log)
        # 运行状态变化时刷新按钮
        self.win.pm.running_changed.connect(lambda _i: self.refresh_running())
        # 运行时长刷新
        self._uptime_timer = QTimer(self)
        self._uptime_timer.timeout.connect(self.refresh_running)
        self._uptime_timer.start(1000)
        # 状态更新（GPU 列表等）
        self.win.statusUpdated.connect(self._on_status)

    # ------------------------------------------------------------ UI
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(14)

        # 左列：参数
        left = QWidget()
        left.setFixedWidth(430)
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # 实例选择
        g_inst = QGroupBox("当前实例")
        f = QFormLayout(g_inst)
        self.cb_instance = QComboBox()
        self.cb_instance.currentIndexChanged.connect(self._on_instance_switch)
        f.addRow("实例:", self.cb_instance)
        self.lb_python = QLabel("—")
        self.lb_python.setProperty("dim", True)
        f.addRow("Python:", self.lb_python)
        lay.addWidget(g_inst)

        # 显存模式
        g_mode = QGroupBox("显存模式")
        mode_lay = QVBoxLayout(g_mode)
        self.cb_mode = QComboBox()
        for key, label, desc in MODES:
            self.cb_mode.addItem(f"{label}  —  {desc}", key)
        self.cb_mode.currentIndexChanged.connect(self._save)
        mode_lay.addWidget(self.cb_mode)
        lay.addWidget(g_mode)

        # 参数
        g_args = QGroupBox("启动参数")
        fa = QFormLayout(g_args)
        self.sp_port = QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.sp_port.setValue(8188)
        self.sp_port.valueChanged.connect(self._save)
        fa.addRow("端口:", self.sp_port)

        self.cb_attention = QComboBox()
        for key, label in ATTENTIONS:
            self.cb_attention.addItem(label, key)
        self.cb_attention.currentIndexChanged.connect(self._save)
        fa.addRow("注意力实现:", self.cb_attention)

        self.cb_gpu = QComboBox()
        self.cb_gpu.addItem("自动", None)
        self.cb_gpu.currentIndexChanged.connect(self._save)
        fa.addRow("GPU 设备:", self.cb_gpu)

        self.ed_extra = QLineEdit()
        self.ed_extra.setPlaceholderText("如 --disable-metadata --multi-user")
        self.ed_extra.textChanged.connect(self._save)
        fa.addRow("额外参数:", self.ed_extra)
        lay.addWidget(g_args)

        # 开关
        g_toggle = QGroupBox("选项")
        tg = QVBoxLayout(g_toggle)
        self.cb_fp16 = QCheckBox("Force FP16")
        self.cb_listen = QCheckBox("监听网络 (--listen)")
        self.cb_autobrowser = QCheckBox("就绪后自动打开浏览器")
        self.cb_autorestart = QCheckBox("异常退出自动重启")
        for cb in (self.cb_fp16, self.cb_listen, self.cb_autobrowser,
                   self.cb_autorestart):
            cb.toggled.connect(self._save)
            tg.addWidget(cb)
        lay.addWidget(g_toggle)

        # 控制
        ctrl = QHBoxLayout()
        self.btn_launch = QPushButton("▶ 启动 ComfyUI")
        self.btn_launch.setObjectName("primary")
        self.btn_launch.setFixedHeight(36)
        self.btn_launch.clicked.connect(self.launch)
        self.btn_stop = QPushButton("■ 停止")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)
        ctrl.addWidget(self.btn_launch, 1)
        ctrl.addWidget(self.btn_stop, 1)
        lay.addLayout(ctrl)

        # 运行状态行：状态文本 + 可复制的地址框
        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        self.lb_run = QLabel("未运行")
        self.lb_run.setProperty("dim", True)
        run_row.addWidget(self.lb_run)
        run_row.addStretch(1)
        self.ed_url = QLineEdit()
        self.ed_url.setReadOnly(True)
        self.ed_url.setFrame(False)
        self.ed_url.setPlaceholderText("启动后显示可复制的访问地址")
        self.ed_url.setStyleSheet(
            "background: transparent; border: none; "
            "selection-background-color: #7c5cff; color: #8fa2b8;")
        self.ed_url.setFixedWidth(220)
        self.ed_url.setVisible(False)
        run_row.addWidget(self.ed_url)
        lay.addLayout(run_row)
        lay.addStretch(1)

        root.addWidget(left)

        # 右列：实时日志
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        t = QLabel("实时日志")
        t.setStyleSheet("font-weight: 600;")
        btn_clear = QPushButton("清空")
        btn_clear.setObjectName("ghost")
        btn_clear.clicked.connect(self.clear_log)
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(btn_clear)
        rl.addLayout(head)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(5000)
        self.console.setPlaceholderText(
            "点击「启动 ComfyUI」后，运行日志将实时显示在这里…")
        rl.addWidget(self.console, 1)
        root.addWidget(right, 1)

    # ------------------------------------------------------------ 数据
    def reload_instances(self):
        cfg = self.win.config
        cur = cfg.current_instance_id
        self.cb_instance.blockSignals(True)
        self.cb_instance.clear()
        for inst in self.win.inst_mgr.all():
            self.cb_instance.addItem(f"{inst.name}  —  {inst.path or inst.url}",
                                     inst.uid)
        # 选中当前实例（或第一个）
        idx = 0
        for i in range(self.cb_instance.count()):
            if self.cb_instance.itemData(i) == cur:
                idx = i
                break
        self.cb_instance.setCurrentIndex(idx)
        self.cb_instance.blockSignals(False)
        self._on_instance_switch()

    def current_instance(self):
        inst = self.win.inst_mgr.get(self.cb_instance.currentData())
        return inst

    def _on_instance_switch(self):
        inst = self.current_instance()
        if inst and inst.is_local:
            self.lb_python.setText(inst.python or "(自动识别/全局设置)")
        else:
            self.lb_python.setText("—")
        self.refresh_running()

    def load_settings_to_ui(self):
        """从配置加载启动参数到控件。

        加载期间必须阻塞控件信号：否则 setValue/setChecked 会触发 _save，
        而尚未加载的控件还是默认状态，会把配置污染成默认值。
        """
        launch = self.win.config.launch
        widgets = (self.cb_mode, self.sp_port, self.cb_attention, self.cb_gpu,
                   self.ed_extra, self.cb_fp16, self.cb_listen,
                   self.cb_autobrowser, self.cb_autorestart)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self.cb_mode.findData(launch.get("mode", "auto"))
            self.cb_mode.setCurrentIndex(max(idx, 0))
            self.sp_port.setValue(int(launch.get("port", 8188)))
            idx = self.cb_attention.findData(launch.get("attention", "auto"))
            self.cb_attention.setCurrentIndex(max(idx, 0))
            idx = self.cb_gpu.findData(launch.get("cuda_device"))
            self.cb_gpu.setCurrentIndex(max(idx, 0))
            self.ed_extra.setText(" ".join(launch.get("extra_args") or []))
            self.cb_fp16.setChecked(bool(launch.get("force_fp16")))
            self.cb_listen.setChecked(bool(launch.get("listen")))
            self.cb_autobrowser.setChecked(bool(launch.get("auto_launch_browser", True)))
            self.cb_autorestart.setChecked(bool(launch.get("auto_restart", True)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        # 加载完成后再统一保存一次，保证配置与 UI 一致
        self._save()

    def _save(self, *_):
        launch = self.win.config.launch
        launch["mode"] = self.cb_mode.currentData()
        launch["port"] = self.sp_port.value()
        launch["attention"] = self.cb_attention.currentData()
        launch["cuda_device"] = self.cb_gpu.currentData()
        launch["extra_args"] = [t for t in self.ed_extra.text().split() if t.strip()]
        launch["force_fp16"] = self.cb_fp16.isChecked()
        launch["listen"] = self.cb_listen.isChecked()
        launch["auto_launch_browser"] = self.cb_autobrowser.isChecked()
        launch["auto_restart"] = self.cb_autorestart.isChecked()
        # 实例切换也记录为当前实例
        uid = self.cb_instance.currentData()
        if uid:
            self.win.config.current_instance_id = uid
        self.win.config.save()

    def _on_status(self, status):
        """主窗口状态轮询结果：刷新 GPU 设备列表。"""
        if not status:
            return
        gpus = status.get("gpus") or []
        cur = self.cb_gpu.currentData()
        self.cb_gpu.blockSignals(True)
        self.cb_gpu.clear()
        self.cb_gpu.addItem("自动", None)
        for i in range(len(gpus)):
            self.cb_gpu.addItem(f"GPU {i}", i)
        idx = self.cb_gpu.findData(cur)
        self.cb_gpu.setCurrentIndex(max(idx, 0))
        self.cb_gpu.blockSignals(False)

    # ------------------------------------------------------------ 操作
    def launch(self):
        inst = self.current_instance()
        if not inst:
            QMessageBox.warning(self, "提示", "请先在「实例管理」中添加并选择实例")
            return
        if not inst.is_local:
            QMessageBox.warning(self, "提示", "远程实例无法在本机启动")
            return
        self._save()
        cfg = self.win.config.launch
        port = int(cfg.get("port", 8188))
        # 端口被非本启动器进程占用：先弹窗确认是否结束占用
        blocker = self.win.pm.port_blocker(inst, cfg)
        if blocker:
            ret = QMessageBox.question(
                self, "端口被占用",
                f"端口 {port} 正被 PID {blocker} 监听（不是由本启动器启动的进程）。\n\n"
                "结束该进程并继续启动吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ret != QMessageBox.Yes:
                self.win.sb("已取消启动")
                return
            self.win.pm.kill_pid_tree(blocker)
            self.win.log(f"已结束占用端口的进程 PID {blocker}")
        self.win.log(f"准备启动 {inst.name} …")
        try:
            info = self.win.pm.launch(inst, cfg, self.win.config.mirrors)
            self.win.sb(f"已启动 {inst.name} (PID {info['pid']})")
        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))
            self.win.log(f"启动失败: {e}")
        self.refresh_running()

    def stop(self):
        def ask_foreign(pids):
            box = QMessageBox(self)
            box.setWindowTitle("确认停止")
            box.setIcon(QMessageBox.Question)
            box.setText("以下进程占用该端口，可能由网页/外部重启产生：")
            box.setInformativeText(
                "PID " + ", ".join(str(p) for p in pids)
                + "\n\n确认结束这些进程吗？")
            btn_yes = box.addButton("结束", QMessageBox.AcceptRole)
            btn_no = box.addButton("取消", QMessageBox.RejectRole)
            box.setDefaultButton(btn_yes)
            box.exec_()
            return box.clickedButton() is btn_yes

        try:
            if not self.win.pm.stop(ask_foreign=ask_foreign):
                self.win.sb("已取消停止")
                return
            self.win.sb("已停止")
        except Exception as e:
            self.win.log(f"停止出错: {e}")
        self.refresh_running()

    def clear_log(self):
        self.console.clear()
        self.win.pm.clear_log()

    def append_log(self, line: str):
        self.console.appendPlainText(line)

    def refresh_running(self):
        info = self.win.pm.running_info()
        if info:
            self.btn_launch.setEnabled(False)
            self.btn_stop.setEnabled(True)
            up = info["uptime_secs"]
            h, rem = divmod(up, 3600)
            m, s = divmod(rem, 60)
            uptime = (f"{h}时{m}分{s}秒" if h else
                      (f"{m}分{s}秒" if m else f"{s}秒"))
            self.lb_run.setProperty("ok", True)
            note = "（已被网页/外部重启接管）" if info.get("adopted") else ""
            self.lb_run.setText(f"运行中 (PID {info['pid']}) · {uptime}{note}")
            # 地址框：可选中复制
            self.ed_url.setText(info["url"])
            self.ed_url.setVisible(True)
        else:
            self.btn_launch.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.lb_run.setProperty("ok", False)
            self.lb_run.setProperty("dim", True)
            self.lb_run.setText("未运行")
            self.ed_url.setVisible(False)
            self.ed_url.clear()
        # 刷新样式属性
        self.lb_run.style().unpolish(self.lb_run)
        self.lb_run.style().polish(self.lb_run)
