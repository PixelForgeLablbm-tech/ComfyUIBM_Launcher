# -*- coding: utf-8 -*-
"""设置页签：默认 Python / 更新检查 / PyPI 镜像 / HF 镜像 / 代理 / 托盘。"""
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from launcher.mirrors import GH_PROXY_PRESETS, PYPI_MIRRORS


class SettingsTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._build()
        self._load()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 10)
        lay.setSpacing(12)
        content = QWidget()
        content.setMaximumWidth(960)
        ml = QVBoxLayout(content)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(12)

        # ---------------- 通用 ----------------
        g1 = QGroupBox("通用")
        g1_lay = QVBoxLayout(g1)
        f = QFormLayout()
        f.setHorizontalSpacing(12)
        f.setVerticalSpacing(9)
        py_row = QHBoxLayout()
        self.ed_python = QLineEdit()
        py_row.addWidget(self.ed_python, 1)
        btn_py = QPushButton("浏览…")
        btn_py.clicked.connect(self._browse_python)
        py_row.addWidget(btn_py)
        f.addRow("默认 Python:", py_row)
        self.cb_theme = QComboBox()
        self.cb_theme.addItem("跟随系统", "system")
        self.cb_theme.addItem("深色", "dark")
        self.cb_theme.addItem("浅色", "light")
        f.addRow("界面主题:", self.cb_theme)
        self.cb_dpi = QComboBox()
        for label, val in (
            ("自动（跟随系统）", "auto"),
            ("关闭（禁用高 DPI）", "off"),
            ("100%", "1.0"),
            ("120%", "1.2"),
            ("125%", "1.25"),
            ("150%", "1.5"),
            ("200%", "2.0"),
        ):
            self.cb_dpi.addItem(label, val)
        f.addRow("DPI 缩放:", self.cb_dpi)
        g1_lay.addLayout(f)
        ml.addWidget(g1)

        # ---------------- 网络 ----------------
        g2 = QGroupBox("网络（镜像 / 代理）")
        g2_lay = QVBoxLayout(g2)
        f2 = QFormLayout()
        f2.setHorizontalSpacing(12)
        f2.setVerticalSpacing(8)
        self.cb_pypi = QComboBox()
        for key, label, _url in PYPI_MIRRORS:
            self.cb_pypi.addItem(label, key)
        f2.addRow("PyPI 镜像:", self.cb_pypi)
        self.cb_hf = QCheckBox("HuggingFace 镜像（HF_ENDPOINT = hf-mirror.com）")
        f2.addRow("", self.cb_hf)
        self.cb_proxy = QCheckBox("启用代理（VPN 用户可关闭直连）")
        f2.addRow("", self.cb_proxy)
        self.ed_proxy = QLineEdit()
        self.ed_proxy.setPlaceholderText("http://127.0.0.1:7890")
        f2.addRow("代理地址:", self.ed_proxy)
        g2_lay.addLayout(f2)

        gh_panel = QFrame()
        gh_panel.setObjectName("settingsGithub")
        gh_lay = QVBoxLayout(gh_panel)
        gh_lay.setContentsMargins(12, 10, 12, 10)
        gh_lay.setSpacing(8)
        gh_title = QLabel("GitHub 加速（国内镜像）")
        gh_title.setObjectName("settingsSectionTitle")
        gh_lay.addWidget(gh_title)
        gh_row = QHBoxLayout()
        gh_row.setSpacing(8)
        self.btn_gh = QPushButton("加速关")
        self.btn_gh.setObjectName("ghost")
        self.btn_gh.setFixedSize(90, 32)
        self.btn_gh.clicked.connect(self.toggle_gh)
        gh_row.addWidget(self.btn_gh)
        self.cb_gh = QComboBox()
        self.cb_gh.setMinimumWidth(230)
        for label, value in GH_PROXY_PRESETS:
            self.cb_gh.addItem(label, value)
        self.cb_gh.addItem("自定义…", "__custom__")
        self.cb_gh.currentIndexChanged.connect(self._on_gh_prefix)
        gh_row.addWidget(self.cb_gh, 1)
        self.ed_gh_custom = QLineEdit()
        self.ed_gh_custom.setPlaceholderText("https://你的加速服务/")
        self.ed_gh_custom.setMinimumWidth(240)
        self.ed_gh_custom.returnPressed.connect(self._save_gh_custom)
        gh_row.addWidget(self.ed_gh_custom)
        gh_lay.addLayout(gh_row)
        g2_lay.addWidget(gh_panel)
        ml.addWidget(g2)

        # ---------------- 应用信息 ----------------
        g3 = QGroupBox("应用信息")
        g3_lay = QVBoxLayout(g3)
        f3 = QFormLayout()
        f3.setHorizontalSpacing(12)
        f3.setVerticalSpacing(7)
        f3.addRow("名称:", QLabel("ComfyUIBM启动器"))
        from launcher import APP_VERSION
        f3.addRow("版本:", QLabel(APP_VERSION))
        f3.addRow("配置文件:", QLabel(str(self.win.config.path)))
        g3_lay.addLayout(f3)
        btn_log = QPushButton("显示运行日志")
        btn_log.setObjectName("ghost")
        btn_log.clicked.connect(self.win.show_log_dock)
        self.btn_update = QPushButton("检查更新")
        self.btn_update.setObjectName("ghost")
        self.btn_update.clicked.connect(self.check_update)
        btn_decl = QPushButton("声明")
        btn_decl.setObjectName("ghost")
        btn_decl.clicked.connect(self.win.show_declaration)
        row = QHBoxLayout()
        row.addWidget(btn_log)
        row.addWidget(self.btn_update)
        row.addWidget(btn_decl)
        row.addStretch(1)
        g3_lay.addLayout(row)
        ml.addWidget(g3)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("保存设置")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self.save)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch(1)
        ml.addLayout(btn_row)
        ml.addStretch(1)
        lay.addWidget(content)

    def _browse_python(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 Python 可执行文件",
                                           self.ed_python.text(),
                                           "Python (python.exe);;所有文件 (*)")
        if f:
            self.ed_python.setText(f)

    def _load(self):
        s = self.win.config.settings
        self.ed_python.setText(s.get("python_path", "python"))
        idx = self.cb_theme.findData(s.get("theme", "dark"))
        self.cb_theme.setCurrentIndex(max(idx, 0))
        idx = self.cb_dpi.findData(str(s.get("dpi_scaling", "auto")))
        self.cb_dpi.setCurrentIndex(max(idx, 0))
        m = self.win.config.mirrors
        idx = self.cb_pypi.findData(m.get("pypi_mirror", "aliyun"))
        self.cb_pypi.setCurrentIndex(max(idx, 0))
        self.cb_hf.setChecked(bool(m.get("hf_mirror")))
        self.cb_proxy.setChecked(bool(m.get("use_proxy")))
        self.ed_proxy.setText(m.get("proxy", ""))
        self.ed_proxy.setEnabled(self.cb_proxy.isChecked())
        self._sync_gh_ui()
        self.cb_proxy.toggled.connect(self.ed_proxy.setEnabled)
        # 主题切换即时生效，无需点「保存设置」
        self.cb_theme.currentIndexChanged.connect(self._on_theme_changed)
        # DPI 缩放选择即自动保存（重启后生效），无需点「保存设置」
        self.cb_dpi.currentIndexChanged.connect(self._on_dpi_changed)

    def _sync_gh_ui(self):
        mirrors = self.win.config.mirrors
        enabled = bool(mirrors.get("gh_proxy"))
        self.btn_gh.setText("加速开" if enabled else "加速关")
        self.btn_gh.setStyleSheet(
            "border-color: #7c5cff; color: #c4b5fd;" if enabled else "")
        prefix = mirrors.get("gh_proxy_prefix", "")
        idx = self.cb_gh.findData(prefix)
        if idx >= 0:
            self.cb_gh.setCurrentIndex(idx)
            self.ed_gh_custom.setVisible(False)
        else:
            self.cb_gh.setCurrentIndex(self.cb_gh.findData("__custom__"))
            self.ed_gh_custom.setText(prefix)
            self.ed_gh_custom.setVisible(True)

    def toggle_gh(self):
        mirrors = self.win.config.mirrors
        mirrors["gh_proxy"] = not mirrors.get("gh_proxy", False)
        self.win.config.save()
        self._sync_gh_ui()
        self.win.sb("已开启 GitHub 加速" if mirrors["gh_proxy"]
                    else "已关闭加速（直连 GitHub）")

    def _on_gh_prefix(self, _idx):
        prefix = self.cb_gh.currentData()
        if prefix == "__custom__":
            self.ed_gh_custom.setVisible(True)
            return
        self.ed_gh_custom.setVisible(False)
        if prefix:
            self.win.config.mirrors["gh_proxy_prefix"] = prefix
            self.win.config.save()

    def _save_gh_custom(self):
        prefix = self.ed_gh_custom.text().strip()
        if prefix:
            self.win.config.mirrors["gh_proxy_prefix"] = prefix
            self.win.config.save()
            self.win.sb("已保存自定义 GitHub 加速地址")

    def _on_dpi_changed(self, _idx):
        """DPI 缩放：选择即保存；提供立即重启，避免选错后界面过大无法操作。"""
        from PyQt5.QtWidgets import QMessageBox
        s = self.win.config.settings
        s["dpi_scaling"] = self.cb_dpi.currentData()
        if not self.win.config.save():
            QMessageBox.warning(self, "保存失败", "无法写入配置文件，DPI 设置未生效")
            return
        box = QMessageBox(self)
        box.setWindowTitle("DPI 缩放")
        box.setIcon(QMessageBox.Question)
        box.setText(f"DPI 缩放已设为：{self.cb_dpi.currentText()}")
        box.setInformativeText("重启启动器后生效。要立即重启吗？")
        btn_restart = box.addButton("立即重启", QMessageBox.AcceptRole)
        btn_later = box.addButton("稍后", QMessageBox.RejectRole)
        box.setDefaultButton(btn_later)
        box.exec_()
        if box.clickedButton() is btn_restart:
            self._restart_app()
        else:
            self.win.sb("DPI 缩放已保存，重启后生效")

    def _restart_app(self):
        """重启启动器（不停止 ComfyUI），用于 DPI 等需重启的设置。
        若有重要后台任务（插件下载/更新等）在跑，先确认避免中断。"""
        import subprocess
        import sys
        from PyQt5.QtWidgets import QApplication, QMessageBox
        if self.win.tasks.active_warn_count() > 0:
            ret = QMessageBox.question(
                self, "确认重启",
                "当前有后台任务正在运行（如插件下载、版本更新）。\n\n"
                "立即重启会中断这些任务，确定要重启吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                self.win.sb("已取消重启，DPI 将在下次启动生效")
                return
        # 清掉 PyInstaller onefile 的父/子进程变量（_PYI_*），否则新版/重启的
        # 引导程序会误判为"子进程"而启动失败（PYI_APPLICATION_HOME_DIR 弹窗等）
        env = dict(os.environ)
        for k in [k for k in env if k.startswith("_PYI_")]:
            env.pop(k, None)
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable], env=env,
                             creationflags=0x08000000 if os.name == "nt" else 0)
        else:
            subprocess.Popen([sys.executable, "main.py"], env=env,
                             creationflags=0x08000000 if os.name == "nt" else 0)
        self.win._updating = True          # 关闭时不询问、不停 ComfyUI
        QApplication.instance().quit()

    def _on_theme_changed(self, _idx):
        theme = self.cb_theme.currentData()
        self.win.config.settings["theme"] = theme
        self.win.config.save()
        self.win.set_theme(theme)

    def check_update(self):
        """检查启动器自身是否有新版本（GitHub Releases）。"""
        import webbrowser
        from launcher import APP_VERSION
        from launcher.self_update import check_latest, has_update
        from PyQt5.QtWidgets import QMessageBox

        self.btn_update.setEnabled(False)
        self.btn_update.setText("检查中…")
        mirrors = dict(self.win.config.mirrors)

        def done(info):
            self.btn_update.setEnabled(True)
            self.btn_update.setText("检查更新")
            latest = info.get("latest_tag", "")
            if not latest:
                QMessageBox.information(
                    self, "检查更新",
                    "GitHub 上还没有发布版本，请先在 Releases 发布 v1.0.0。")
                return
            if has_update(APP_VERSION, latest):
                ret = QMessageBox.question(
                    self, "发现新版本",
                    f"当前版本：v{APP_VERSION}\n"
                    f"最新版本：{latest}\n\n"
                    f"{info.get('name') or ''}\n\n"
                    "是否下载并更新？（下载完成后程序将自动重启生效）",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if ret == QMessageBox.Yes:
                    self._download_and_apply(info)
            else:
                QMessageBox.information(
                    self, "检查更新", f"已是最新版本：v{APP_VERSION}")

        def fail(err):
            self.btn_update.setEnabled(True)
            self.btn_update.setText("检查更新")
            QMessageBox.warning(
                self, "检查更新失败",
                f"{err}\n\n提示：可到「设置 → 网络」启用代理，或开启 GitHub 加速后重试。")

        self.win.tasks.start(
            lambda report, m=mirrors: check_latest(m),
            on_done=done,
            on_error=fail,
            warn_on_close=False,      # 秒级检查，关闭时无需提醒
        )

    def _download_and_apply(self, info):
        """下载新版单文件 exe，写替换批处理，重启生效。"""
        import subprocess
        import sys
        import tempfile
        import webbrowser
        from PyQt5.QtCore import Qt as _Qt
        from PyQt5.QtWidgets import QApplication, QProgressDialog

        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self, "提示",
                "当前为开发模式运行，无法直接替换程序。\n"
                "请前往 GitHub Releases 下载安装包。")
            webbrowser.open(info.get("html_url", ""))
            return

        from launcher.self_update import asset_url, download
        url = asset_url(info, "ComfyUIBM_Launcher.exe")
        if not url:
            QMessageBox.warning(
                self, "更新失败",
                "Release 中未找到主程序资产 ComfyUIBM_Launcher.exe，\n"
                "请先上传单文件版主程序。")
            return

        mirrors = dict(self.win.config.mirrors)
        dest = Path(tempfile.gettempdir()) / "ComfyUIBM_new.exe"

        dlg = QProgressDialog("正在下载更新…", "取消", 0, 0, self)
        dlg.setWindowTitle("下载更新")
        dlg.setWindowModality(_Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)

        def work(report):
            download(url, str(dest), mirrors,
                     progress=lambda d, t: report(
                         f"正在下载更新… {d // (1 << 20)}/{t // (1 << 20)} MB"))
            return str(dest)

        def on_progress(msg):
            dlg.setLabelText(msg)

        def on_done(path):
            dlg.close()
            exe = Path(sys.executable).resolve()
            exe_dir = exe.parent
            err_log = Path(tempfile.gettempdir()) / "ComfyUIBM_update_err.log"
            bat = Path(tempfile.gettempdir()) / "ComfyUIBM_update.bat"
            bat.write_text(
                # 大厂式"改名让位"更新：不覆盖运行中的 exe（Windows 允许重命名
                # 运行中的 exe，但不允许覆盖），改名腾位 → 新文件就位 → 删旧文件。
                # 完全不依赖旧进程何时退出，一次成功。
                # 先清掉 PyInstaller 的 _PYI_* 环境变量：本进程继承自旧版 onefile
                # 的父/子进程变量会让新版引导程序误判"子进程"而启动失败
                # （PYI_APPLICATION_HOME_DIR / Security validation failure 等弹窗）。
                "@echo off\r\n"
                "set _PYI_ARCHIVE_FILE=\r\n"
                "set _PYI_PARENT_PROCESS_LEVEL=\r\n"
                "set _PYI_APPLICATION_HOME_DIR=\r\n"
                "set _PYI_SPLASH_IPC=\r\n"
                f'move /y "{exe}" "{exe}.old" >nul 2>&1\r\n'
                "if errorlevel 1 (\r\n"
                f'  echo UPDATE_RENAME_FAILED {exe} >> "{err_log}"\r\n'
                f'  start "" "{exe}"\r\n'
                f'  del "{path}" >nul 2>&1\r\n'
                '  del "%~f0" >nul 2>&1\r\n'
                "  exit /b 1\r\n"
                ")\r\n"
                f'copy /y "{path}" "{exe}" >nul 2>&1\r\n'
                "if errorlevel 1 (\r\n"
                f'  move /y "{exe}.old" "{exe}" >nul 2>&1\r\n'
                f'  echo UPDATE_COPY_FAILED {path} >> "{err_log}"\r\n'
                f'  start "" "{exe}"\r\n'
                f'  del "{path}" >nul 2>&1\r\n'
                '  del "%~f0" >nul 2>&1\r\n'
                "  exit /b 1\r\n"
                ")\r\n"
                f'del "{exe}.old" >nul 2>&1\r\n'
                f'del "{path}" >nul 2>&1\r\n'
                f'if exist "{exe_dir}\\_internal" rmdir /s /q "{exe_dir}\\_internal" >nul 2>&1\r\n'
                f'start "" "{exe}"\r\n'
                'del "%~f0" >nul 2>&1\r\n',
                encoding="ascii", errors="replace")
            subprocess.Popen(
                ["cmd", "/c", "start", "", "/b", str(bat)],
                creationflags=0x08000000 if os.name == "nt" else 0)
            self.win._updating = True
            QMessageBox.information(
                self, "更新完成",
                "新版本已下载，程序即将退出并在重启后生效。")
            QApplication.instance().quit()

        def on_error(err):
            dlg.close()
            QMessageBox.critical(self, "下载失败", str(err))

        self.win.tasks.start(work, on_progress=on_progress,
                             on_done=on_done, on_error=on_error)

    def save(self):
        s = self.win.config.settings
        s["python_path"] = self.ed_python.text().strip() or "python"
        theme = self.cb_theme.currentData()
        s["dpi_scaling"] = self.cb_dpi.currentData()
        m = self.win.config.mirrors
        m["pypi_mirror"] = self.cb_pypi.currentData()
        m["hf_mirror"] = self.cb_hf.isChecked()
        m["use_proxy"] = self.cb_proxy.isChecked()
        m["proxy"] = self.ed_proxy.text().strip()
        if self.win.config.save():
            self.win.set_theme(theme)   # 立即切换主题
            self.win.sb("设置已保存")
            self.win.log("设置已保存")
        else:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "保存失败", f"无法写入配置文件:\n{self.win.config.path}")
