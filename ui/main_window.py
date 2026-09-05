# -*- coding: utf-8 -*-
"""主窗口：侧边栏导航 + 顶栏状态条 + 六页签 + 托盘 + 窗口状态记忆。"""
from datetime import datetime

from PyQt5.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt5.QtGui import QCloseEvent, QIcon, QPixmap, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QDockWidget, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from launcher import APP_VERSION, system_info
from launcher.config import Config
from launcher.instance_manager import InstanceManager
from launcher.process_manager import ProcessManager
from launcher.tasks import TaskManager

from ui.launch_tab import LaunchTab
from ui.instances_tab import InstancesTab
from ui.models_tab import ModelsTab
from ui.plugins_tab import PluginsTab
from ui.workflow_tab import WorkflowTab
from ui.update_tab import UpdateTab
from ui.kernel_tab import KernelTab
from ui.files_tab import FilesTab
from ui.settings_tab import SettingsTab

APP_TITLE = f"ComfyUIBM启动器 v{APP_VERSION}"


class _ClickLabel(QLabel):
    """可点击的纯文字标签（点击发射 clicked 信号）。"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    statusUpdated = pyqtSignal(object)   # 状态轮询结果 dict

    def __init__(self, config_path=None):
        super().__init__()
        self.config = Config(config_path)
        self.inst_mgr = InstanceManager(self.config)
        self.tasks = TaskManager()
        self.pm = ProcessManager(self)
        self.status = {}
        self._settings = QSettings("ComfyUILauncher", "ComfyUILauncher")

        self.setWindowTitle(APP_TITLE)
        self.resize(1033, 807)
        self._restore_geometry()
        self._updating = False      # 一键更新重启标志

        self._build_shell()
        self._build_log_dock()
        self._build_tray()

        # 信号
        self.pm.log_line.connect(self._on_comfy_log)
        self.pm.ready.connect(self._on_ready)
        self.pm.exited.connect(self._on_exited)
        self.pm.running_changed.connect(self._on_running_changed)

        self.reload_all()

        # 应用主题（浅色/深色/跟随系统）
        self._theme_name = "dark"
        self._theme_timer = None
        self._last_system_dark = False
        self._apply_theme()

        # 状态轮询
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.poll_status)
        self._status_timer.start(4000)
        QTimer.singleShot(800, self.poll_status)

        # 启动后静默检查启动器自身版本
        self._latest_info = None
        QTimer.singleShot(3000, self._check_version_badge)

        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------ 构建
    def _build_shell(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 侧边栏
        self.side = QListWidget()
        self.side.setObjectName("sideNav")
        self.side.setFixedWidth(168)
        items = [
            ("启动控制台", 0),
            ("实例管理", 1),
            ("模型管理", 2),
            ("插件管理", 3),
            ("更新维护", 4),
            ("内核维护", 5),
            ("文件管理", 6),
            ("工作流识别", 7),
            ("设置", 8),
        ]
        for label, idx in items:
            item = QListWidgetItem("  " + label)
            item.setData(Qt.UserRole, idx)
            self.side.addItem(item)

        # 左侧容器：导航 + 左下角版本提示（背景与侧边栏统一）
        left = QWidget()
        left.setObjectName("sidePanel")
        left.setFixedWidth(168)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        ll.addWidget(self.side, 1)
        self.lb_version = _ClickLabel("版本检查中…")
        self.lb_version.setProperty("dim", True)
        self.lb_version.setCursor(Qt.PointingHandCursor)
        self.lb_version.setToolTip("点击重新检查 / 有新版时点击更新")
        self.lb_version.setStyleSheet(
            "background: transparent; padding: 6px 12px; font-size: 11px;")
        self.lb_version.clicked.connect(self._on_version_badge_click)
        ll.addWidget(self.lb_version)
        root.addWidget(left)

        # 右侧：顶栏 + 内容
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self._build_topbar(rl)

        self.stack = QStackedWidget()
        self.launch_tab = LaunchTab(self)
        self.instances_tab = InstancesTab(self)
        self.models_tab = ModelsTab(self)
        self.plugins_tab = PluginsTab(self)
        self.workflow_tab = WorkflowTab(self)
        self.update_tab = UpdateTab(self)
        self.kernel_tab = KernelTab(self)
        self.files_tab = FilesTab(self)
        self.settings_tab = SettingsTab(self)
        for tab in (self.launch_tab, self.instances_tab, self.models_tab,
                    self.plugins_tab, self.update_tab, self.kernel_tab,
                    self.files_tab, self.workflow_tab, self.settings_tab):
            self.stack.addWidget(tab)
        rl.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self.side.currentRowChanged.connect(self._nav)
        self.side.setCurrentRow(0)
        self.setCentralWidget(central)

    def _build_topbar(self, parent_layout):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFrameShape(QFrame.NoFrame)
        bar.setFixedHeight(46)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.setSpacing(12)

        self.chip_port = QLabel("端口 8188 未监听")
        self.chip_port.setStyleSheet(self._chip_style())
        hl.addWidget(self.chip_port)
        self.chip_inst = QLabel("")
        self.chip_inst.setStyleSheet(self._chip_style())
        hl.addWidget(self.chip_inst)
        hl.addStretch(1)
        self.chip_gpu = QLabel("")
        self.chip_gpu.setStyleSheet(self._chip_style())
        hl.addWidget(self.chip_gpu)
        self.chip_ram = QLabel("")
        self.chip_ram.setStyleSheet(self._chip_style())
        hl.addWidget(self.chip_ram)
        parent_layout.addWidget(bar)

    # ------------------------------------------------------------ 主题
    def _is_dark_now(self) -> bool:
        from ui.theme import system_is_dark
        name = self.config.settings.get("theme", "dark")
        if name == "light":
            return False
        if name == "system":
            return system_is_dark()
        return True

    def _chip_style(self, ok=None):
        dark = self._is_dark_now()
        base = "#42566e" if dark else "#eceef2"
        txt = "#d8dee9" if dark else "#2c313a"
        if ok is None:
            return (f"padding: 3px 10px; border-radius: 11px; font-size: 12px; "
                    f"background: {base}; color: {txt};")
        if ok:
            bg = "rgba(52,211,153,0.15)" if dark else "rgba(14,159,110,0.12)"
            color = "#34d399" if dark else "#0e9f6e"
        else:
            bg, color = base, txt
        return (f"padding: 3px 10px; border-radius: 11px; font-size: 12px; "
                f"background: {bg}; color: {color};")

    def _apply_theme(self):
        name = self.config.settings.get("theme", "dark")
        from ui.theme import apply_theme, system_is_dark
        apply_theme(QApplication.instance(), name)
        self._theme_name = name
        # 跟随系统：定时轮询注册表深浅色变化
        if name == "system":
            self._last_system_dark = system_is_dark()
            if not hasattr(self, "_theme_timer") or self._theme_timer is None:
                self._theme_timer = QTimer(self)
                self._theme_timer.timeout.connect(self._poll_system_theme)
            self._theme_timer.start(3000)
        else:
            if hasattr(self, "_theme_timer") and self._theme_timer is not None:
                self._theme_timer.stop()
        self._refresh_chip_colors()

    def _poll_system_theme(self):
        from ui.theme import apply_theme, system_is_dark
        dark = system_is_dark()
        if dark != self._last_system_dark:
            self._last_system_dark = dark
            apply_theme(QApplication.instance(), "system")
            self._refresh_chip_colors()

    def _refresh_chip_colors(self):
        for chip in (self.chip_port, self.chip_inst, self.chip_gpu,
                     self.chip_ram):
            chip.setStyleSheet(self._chip_style())
        self._update_topbar(self.status)

    def set_theme(self, name: str):
        self.config.settings["theme"] = name
        self.config.save()
        self._apply_theme()
        self.log(f"主题已切换: {name}")

    def _build_log_dock(self):
        dock = QDockWidget("运行日志", self)
        dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        btn_clear = QPushButton("清空日志")
        btn_clear.setObjectName("ghost")
        btn_clear.setFixedWidth(100)
        btn_clear.clicked.connect(self.log_view.clear)
        lay.addWidget(self.log_view, 1)
        lay.addWidget(btn_clear, 0, Qt.AlignRight)
        dock.setWidget(box)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [170], Qt.Vertical)
        self.log_dock = dock
        # 默认隐藏，需要时从「设置 → 显示运行日志」恢复
        dock.hide()

    def show_log_dock(self):
        self.log_dock.show()
        self.log_dock.raise_()

    def _load_app_icon(self):
        """优先加载 assets/icon.png（随包分发），缺失时自绘兜底图标。"""
        from pathlib import Path
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            try:
                return QIcon(str(icon_path))
            except Exception:
                pass
        # 兜底：自绘（紫色圆角方块 + 闪电）
        from PyQt5.QtGui import QColor, QPainter
        icon = QIcon()
        for size in (32, 64, 128):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#7c5cff"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(2, 2, size - 4, size - 4,
                                    size // 5, size // 5)
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setPixelSize(int(size * 0.55))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pm.rect(), Qt.AlignCenter, "⚡")
            painter.end()
            icon.addPixmap(pm)
        return icon

    def _build_tray(self):
        icon = self._load_app_icon()
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        act_show = menu.addAction("显示主窗口")
        act_show.triggered.connect(self._show_from_tray)
        act_quit = menu.addAction("退出（停止 ComfyUI）")
        act_quit.triggered.connect(self._quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    # ------------------------------------------------------------ 导航
    def _nav(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)

    # ------------------------------------------------------------ 刷新
    def reload_all(self):
        # 注意：启动时不做盘符扫描，需要时到「实例管理」点「重新扫描」
        self.instances_tab.reload()
        self.launch_tab.reload_instances()
        self.launch_tab.load_settings_to_ui()
        self.update_tab.reload()
        self.workflow_tab.reload()
        self.kernel_tab.reload()
        self.files_tab.reload()
        self._update_chip_inst()

    def instances_changed(self, select_uid=None):
        self.instances_tab.reload()
        self.launch_tab.reload_instances()
        self.update_tab.reload()
        self.files_tab.reload()
        # 实例列表变化会改变当前实例 → 同步刷新模型/插件页（空则禁用、加实例恢复）
        self.models_tab.on_instance_changed()
        self.plugins_tab.on_instance_changed()
        self._update_chip_inst()

    def selected_instance(self):
        """当前实例 = 配置中的 current_instance_id（回退到第一个）。"""
        cfg = self.config
        if cfg.current_instance_id:
            inst = self.inst_mgr.get(cfg.current_instance_id)
            if inst:
                return inst
        insts = self.inst_mgr.all()
        return insts[0] if insts else None

    # ------------------------------------------------------------ 状态轮询
    def poll_status(self):
        def work(report):
            port = int(self.config.launch.get("port", 8188))
            info = self.pm.running_info()
            return {
                "running": info is not None,
                "port": info["port"] if info else port,
                "port_open": system_info.port_open(
                    info["port"] if info else port),
                "gpus": system_info.gpu_info(),
                "ram_total": 0,
                "ram_used": 0,
            }, system_info.ram_info()

        def done(res):
            st, (ram_total, ram_used) = res
            st["ram_total"], st["ram_used"] = ram_total, ram_used
            self.status = st
            self.statusUpdated.emit(st)
            self._update_topbar(st)

        self.tasks.start(work, on_done=done, warn_on_close=False)

    def _update_topbar(self, st):
        if not st:
            return
        port = st.get("port", 8188)
        state = "已监听" if st.get("port_open") else "未监听"
        self.chip_port.setText(f"端口 {port} {state}")
        self.chip_port.setStyleSheet(self._chip_style(ok=st.get("port_open")))
        gpus = st.get("gpus") or []
        if gpus:
            g = gpus[0]
            # nvidia-smi 返回的显存单位是 MiB，直接按 MB 显示
            self.chip_gpu.setText(
                f"{g['name']} · {g['mem_used']:.0f}/{g['mem_total']:.0f}MB "
                f"· {g['util']:.0f}% · {g['temp']:.0f}°C")
            self.chip_gpu.setVisible(True)
        else:
            self.chip_gpu.setVisible(False)
        if st.get("ram_total"):
            pct = min(100, round(st["ram_used"] / st["ram_total"] * 100))
            self.chip_ram.setText(f"内存 {pct}%")
            self.chip_ram.setVisible(True)
        else:
            self.chip_ram.setVisible(False)

    def _update_chip_inst(self):
        inst = self.selected_instance()
        self.chip_inst.setText(f"实例：{inst.name}" if inst else "未配置实例")

    # ------------------------------------------------------------ 进程信号
    def _on_comfy_log(self, line):
        self.log_view.appendPlainText(line)
        self.log_view.moveCursor(QTextCursor.End)
        if self.stack.currentIndex() == 0:
            pass  # launch_tab 自己已连接 console

    def _on_ready(self, url):
        self.log(f"ComfyUI 已就绪：{url}")
        self.sb(f"ComfyUI 已就绪：{url}")

    def _on_exited(self, code):
        self.poll_status()

    def _on_running_changed(self, info):
        self._update_chip_inst()

    # ------------------------------------------------------------ 版本提示
    def _check_version_badge(self):
        from launcher import self_update
        mirrors = dict(self.config.mirrors)

        def done(info):
            self._latest_info = info
            latest = info.get("latest_tag", "")
            if latest and self_update.has_update(APP_VERSION, latest):
                self.lb_version.setText(f"⚠ 新版本 {latest}")
                self.lb_version.setStyleSheet(
                    "background: transparent; padding: 6px 12px; font-size: 11px; "
                    "color: #eab308; font-weight: 600;")
                self.lb_version.setToolTip(f"发现新版本 {latest}，点击更新")
            elif latest:
                self.lb_version.setText(f"✓ 已是最新 v{APP_VERSION}")
                self.lb_version.setStyleSheet(
                    "background: transparent; padding: 6px 12px; font-size: 11px; color: #34d399;")
            else:
                self.lb_version.setText("版本检查失败")
                self.lb_version.setStyleSheet(
                    "background: transparent; padding: 6px 12px; font-size: 11px; color: #8b96a8;")

        def fail(e):
            self.lb_version.setText("版本检查失败")
            self.lb_version.setStyleSheet(
                "background: transparent; padding: 6px 12px; font-size: 11px; color: #8b96a8;")
            self.lb_version.setToolTip(str(e))

        self.tasks.start(
            lambda report, m=mirrors: self_update.check_latest(m),
            on_done=done, on_error=fail, warn_on_close=False)

    def _on_version_badge_click(self):
        from launcher import self_update
        info = getattr(self, "_latest_info", None)
        if info and self_update.has_update(APP_VERSION,
                                           info.get("latest_tag", "")):
            # 有新版：走设置页的确认+下载+重启流程
            self.settings_tab.check_update()
        else:
            self.lb_version.setText("版本检查中…")
            self._check_version_badge()

    # ------------------------------------------------------------ 托盘
    def _quit_app(self):
        """真正退出：先停止正在运行的 ComfyUI。"""
        if self.pm.is_running():
            self.log("正在停止 ComfyUI …")
            self.pm.stop()
        self.pm.shutdown()
        QApplication.instance().quit()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent):
        self._settings.setValue("geometry", self.saveGeometry())
        if getattr(self, "_updating", False):
            # 更新重启：直接退出（不停 ComfyUI，替换的是启动器自身 exe）
            event.accept()
            return
        if self.tasks.active_warn_count() > 0:
            # 后台任务运行中（安装/更新等）：提醒，避免线程随应用退出被销毁
            box = QMessageBox(self)
            box.setWindowTitle("退出确认")
            box.setIcon(QMessageBox.Warning)
            box.setText("后台任务正在运行（如安装/更新内核组件）。")
            box.setInformativeText("退出会中断任务，确定要退出吗？")
            btn_quit = box.addButton("退出", QMessageBox.AcceptRole)
            btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
            box.setDefaultButton(btn_cancel)
            box.exec_()
            if box.clickedButton() is not btn_quit:
                event.ignore()
                return
        running = self.pm.is_running()
        if not running:
            # 未运行：直接关闭，不留后台
            self._quit_app()
            event.accept()
            return
        # ComfyUI 运行中：弹确认提示（会同时停止它）
        box = QMessageBox(self)
        box.setWindowTitle("退出确认")
        box.setIcon(QMessageBox.Question)
        box.setText("ComfyUI 正在运行，关闭软件会同时停止它。")
        box.setInformativeText("确定要退出吗？")
        btn_quit = box.addButton("退出", QMessageBox.AcceptRole)
        btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec_()
        if box.clickedButton() is btn_quit:
            self._quit_app()
            event.accept()
        else:
            event.ignore()

    def _restore_geometry(self):
        geo = self._settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    # ------------------------------------------------------------ 辅助
    def log(self, msg: str):
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        self.log_view.appendPlainText(line)
        self.log_view.moveCursor(QTextCursor.End)

    def sb(self, msg: str):
        self.statusBar().showMessage(msg, 8000)

    def show_declaration(self):
        """声明对话框：版权 / 免责 / 用户协议（长文本可滚动查看）。"""
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                     QScrollArea, QVBoxLayout)
        html = (
            f"<h3>{APP_TITLE}</h3>"
            "<p><b>作者：</b>QQ 570706080</p>"
            "<hr>"
            "<h4>一、版权声明</h4>"
            "<p>本软件（ComfyUIBM启动器，以下简称“本软件”）由作者开发并提供，"
            "源代码及发布形式的版权归作者所有。未经作者许可，不得对本软件进行"
            "反向工程、修改后重新发布或用于商业盈利用途（个人学习、内部使用除外）。</p>"
            "<h4>二、软件性质</h4>"
            "<p>本软件是一款基于 Python + PyQt5 的 ComfyUI 本地管理工具，"
            "仅提供实例管理、模型管理、版本更新、插件管理等辅助功能。"
            "本软件为开源思路的本地工具，不会上传、收集、存储您的任何个人数据或模型文件。</p>"
            "<h4>三、免责声明</h4>"
            "<p>1. 本软件按“现状”提供，作者不对其适用性、可靠性及无错误性作任何明示或暗示的保证。</p>"
            "<p>2. 因使用本软件（包括但不限于：启动/停止 ComfyUI、更新/回滚版本、"
            "安装/更新插件、导入/删除模型文件等操作）而造成的任何直接或间接损失"
            "（包括数据丢失、程序损坏等），作者不承担任何责任。</p>"
            "<p>3. 版本更新、插件安装等操作涉及第三方代码，其风险由使用者自行评估与承担。</p>"
            "<p>4. 使用本软件需自备 git、Python 及 ComfyUI 环境；"
            "因网络、系统环境等外部因素导致的功能异常，不属于软件缺陷。</p>"
            "<h4>四、用户协议</h4>"
            "<p>使用本启动器即代表您已阅读并同意以下用户协议：</p>"
            "<p>您不得实施包括但不限于以下行为，也不得为任何违反法律法规的行为提供便利：</p>"
            "<p>1. 反对宪法所规定的基本原则的。<br>"
            "2. 危害国家安全，泄露国家秘密，颠覆国家政权，破坏国家统一的。<br>"
            "3. 损害国家荣誉和利益的。<br>"
            "4. 煽动民族仇恨、民族歧视，破坏民族团结的。<br>"
            "5. 破坏国家宗教政策，宣扬邪教和封建迷信的。<br>"
            "6. 散布谣言，扰乱社会秩序，破坏社会稳定的。<br>"
            "7. 散布淫秽、色情、赌博、暴力、凶杀、恐怖或教唆犯罪的。<br>"
            "8. 侮辱或诽谤他人，侵害他人合法权益的。<br>"
            "9. 实施任何违背“七条底线”的行为。<br>"
            "10. 含有法律、行政法规禁止的其他内容的。</p>"
            "<h4>五、责任承担</h4>"
            "<p>因您的数据的产生、收集、处理、使用等任何相关事项存在违反法律法规等情况"
            "而造成的全部结果及责任均由您自行承担。</p>"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("声明")
        dlg.resize(580, 660)
        lay = QVBoxLayout(dlg)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        text = QLabel(html)
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setStyleSheet("background: transparent;")
        scroll.setWidget(text)
        lay.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec_()
