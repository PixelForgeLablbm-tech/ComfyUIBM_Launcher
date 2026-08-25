# -*- coding: utf-8 -*-
"""ComfyUIBM启动器 安装向导程序。

功能：选择安装路径、创建桌面/开始菜单快捷方式、安装进度、完成。
打包：pyinstaller -w -n ComfyUIBM_Launcher_Setup --icon assets/icon.ico \\
       --add-data "dist/ComfyUIBM_Launcher;app" --add-data "assets;assets" installer/installer.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWizard, QWizardPage,
)

APP_NAME = "ComfyUIBM启动器"
EXE_NAME = "ComfyUIBM_Launcher.exe"
DEFAULT_DIR = str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) /
                  "Programs" / "ComfyUIBM_Launcher")

# 打包后源文件在 sys._MEIPASS/app；源码运行时在项目 dist/ 下（目录版或单文件版）
def source_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    cands = [
        base / "app",                       # 安装器打包内置
        base / "dist" / "ComfyUIBM_Launcher",
        base / "dist" / "ComfyUIBM_Launcher.exe",
        base / "ComfyUIBM_Launcher.exe",
    ]
    for c in cands:
        if c.is_dir() and (c / EXE_NAME).exists():
            return c
        if c.is_file() and c.name == EXE_NAME:
            return c.parent                # 单文件版：返回所在目录
    raise RuntimeError("找不到要安装的程序文件（app 资源缺失）")


def uninstall_source() -> Path:
    """卸载程序源（Uninstall.exe）：打包内置 uninstall/ 或源码 uninstaller_dist/。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for c in (base / "uninstall" / "Uninstall.exe",
              base / "uninstaller_dist" / "Uninstall.exe"):
        if c.exists():
            return c
    return None


# ---------------------------------------------------------------- 安装线程
class InstallWorker(QThread):
    progress = pyqtSignal(int, int, str)   # 当前 / 总数 / 文件名
    done = pyqtSignal(str)                 # 目标目录 或 "ERR:..."

    def __init__(self, src: Path, dst: Path, uninst: Path = None):
        super().__init__()
        self.src, self.dst = src, dst
        self.uninst = uninst

    def run(self):
        try:
            self.dst.mkdir(parents=True, exist_ok=True)
            files = [f for f in self.src.rglob("*") if f.is_file()]
            if self.uninst and self.uninst.exists():
                files = files + [self.uninst]
            total = len(files)
            for i, f in enumerate(files):
                if self.uninst and f == self.uninst:
                    target = self.dst / "Uninstall.exe"
                else:
                    rel = f.relative_to(self.src)
                    target = self.dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(target))
                self.progress.emit(i + 1, total, str(target.name))
            self.done.emit(str(self.dst))
        except Exception as e:
            self.done.emit("ERR:" + str(e))


def create_shortcut(lnk_path: Path, target: Path, workdir: Path) -> bool:
    """用 PowerShell COM 创建 .lnk 快捷方式。"""
    try:
        ps = (
            "$ws = New-Object -ComObject WScript.Shell\n"
            f"$sc = $ws.CreateShortcut('{lnk_path}')\n"
            f"$sc.TargetPath = '{target}'\n"
            f"$sc.WorkingDirectory = '{workdir}'\n"
            f"$sc.IconLocation = '{target},0'\n"
            "$sc.Save()\n"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=True, timeout=60,
                       creationflags=0x08000000 if os.name == "nt" else 0)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 页面
class WelcomePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("欢迎使用 ComfyUIBM启动器")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "本向导将安装 ComfyUIBM启动器 到您的电脑。\n\n"
            "功能：实例绑定 · 启动控制台 · 模型管理 · 插件管理 · "
            "版本更新 · 文件管理 · 插件搜索。\n\n"
            "点击「下一步」继续。"))


class OptionsPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("安装选项")
        self.setSubTitle("选择安装位置与快捷方式")
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("安装目录："))
        row = QHBoxLayout()
        self.ed_dir = QLineEdit(DEFAULT_DIR)
        btn = QPushButton("浏览…")
        btn.clicked.connect(self._browse)
        row.addWidget(self.ed_dir, 1)
        row.addWidget(btn)
        lay.addLayout(row)

        self.cb_desktop = QCheckBox("创建桌面快捷方式")
        self.cb_desktop.setChecked(True)
        self.cb_menu = QCheckBox("创建开始菜单快捷方式")
        self.cb_menu.setChecked(True)
        lay.addWidget(self.cb_desktop)
        lay.addWidget(self.cb_menu)
        lay.addStretch(1)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择安装目录",
                                             self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def validatePage(self):
        d = self.ed_dir.text().strip()
        if not d:
            return False
        self.wizard().options = {
            "dir": d,
            "desktop": self.cb_desktop.isChecked(),
            "menu": self.cb_menu.isChecked(),
        }
        return True


class InstallPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("正在安装")
        self.setSubTitle("复制文件到安装目录…")
        lay = QVBoxLayout(self)
        self.lb_status = QLabel("准备安装…")
        self.pb = QProgressBar()
        lay.addWidget(self.lb_status)
        lay.addWidget(self.pb)
        self.btn_start = QPushButton("开始安装")
        self.btn_start.clicked.connect(self.start_install)
        lay.addWidget(self.btn_start)
        self._worker = None
        self._ok = False

    def initializePage(self):
        self._ok = False
        self.pb.setValue(0)
        self.lb_status.setText("准备安装…")
        self.btn_start.setEnabled(True)

    def start_install(self):
        opt = self.wizard().options
        self.btn_start.setEnabled(False)
        try:
            src = source_dir()
            uninst = uninstall_source()
        except RuntimeError as e:
            self.lb_status.setText(str(e))
            return
        self._worker = InstallWorker(src, Path(opt["dir"]), uninst)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, cur, total, name):
        self.pb.setMaximum(total)
        self.pb.setValue(cur)
        self.lb_status.setText(f"({cur}/{total}) {name}")

    def _on_done(self, result):
        if result.startswith("ERR:"):
            self.lb_status.setText("安装失败：" + result[4:])
            self.btn_start.setEnabled(True)
            return
        opt = self.wizard().options
        exe = Path(result) / EXE_NAME
        uninst_exe = Path(result) / "Uninstall.exe"
        ok_msg = []
        if opt["desktop"]:
            lnk = Path.home() / "Desktop" / f"{APP_NAME}.lnk"
            ok_msg.append("桌面快捷方式" if create_shortcut(lnk, exe, Path(result))
                          else "桌面快捷方式(失败)")
        if opt["menu"]:
            menu = Path(os.environ.get("APPDATA", str(Path.home()))) / \
                "Microsoft" / "Windows" / "Start Menu" / "Programs"
            lnk = menu / f"{APP_NAME}.lnk"
            ok_msg.append("开始菜单快捷方式" if create_shortcut(lnk, exe, Path(result))
                          else "开始菜单快捷方式(失败)")
            if uninst_exe.exists():
                un_lnk = menu / f"卸载 {APP_NAME}.lnk"
                create_shortcut(un_lnk, uninst_exe, Path(result))
        self.lb_status.setText("安装完成。\n" + "，".join(ok_msg))
        self._ok = True
        self.wizard().installed_dir = result

    def isComplete(self):
        return self._ok

    def isFinalPage(self):
        return True


class FinishPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("安装完成")
        lay = QVBoxLayout(self)
        self.lb = QLabel("ComfyUIBM启动器 已安装成功！")
        self.cb_run = QCheckBox("立即运行 ComfyUIBM启动器")
        self.cb_run.setChecked(True)
        lay.addWidget(self.lb)
        lay.addWidget(self.cb_run)
        lay.addStretch(1)

    def initializePage(self):
        d = getattr(self.wizard(), "installed_dir", "")
        self.lb.setText(f"ComfyUIBM启动器 已安装成功！\n安装目录：{d}")


# ---------------------------------------------------------------- 向导
class InstallWizard(QWizard):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"安装 {APP_NAME}")
        self.setWizardStyle(QWizard.ModernStyle)
        self.options = {}
        self.installed_dir = ""
        self.setWindowIcon(self.windowIcon())
        self.addPage(WelcomePage())
        self.addPage(OptionsPage())
        self.addPage(InstallPage())
        self.addPage(FinishPage())
        self.setMinimumSize(560, 420)
        self.button(QWizard.FinishButton).clicked.connect(self._on_finish)

    def _on_finish(self):
        run_page = self.page(3)
        if getattr(run_page, "cb_run", None) and run_page.cb_run.isChecked():
            exe = Path(self.installed_dir) / EXE_NAME
            if exe.exists():
                os.startfile(str(exe))  # noqa


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ComfyUIBM启动器 安装程序")
    try:
        from PyQt5.QtGui import QIcon
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        ico = base / "assets" / "icon.ico"
        if ico.exists():
            app.setWindowIcon(QIcon(str(ico)))
    except Exception:
        pass
    w = InstallWizard()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
