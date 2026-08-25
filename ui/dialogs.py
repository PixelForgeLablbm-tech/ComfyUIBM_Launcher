# -*- coding: utf-8 -*-
"""对话框集合：实例编辑、插件安装、Torch 安装。"""
import re
from pathlib import Path

from PyQt5.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QMessageBox, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from launcher.instance import Instance, TYPE_LOCAL, TYPE_REMOTE
from launcher.instance_scanner import find_python


def confirm(parent, title: str, text: str) -> bool:
    ret = QMessageBox.question(parent, title, text,
                               QMessageBox.Yes | QMessageBox.No,
                               QMessageBox.No)
    return ret == QMessageBox.Yes


def open_in_explorer(parent, path: str) -> None:
    """在系统文件管理器中打开路径。"""
    import os
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices
    path = str(path)
    if os.name == "nt" and os.path.isdir(path):
        try:
            os.startfile(path)  # noqa
            return
        except OSError:
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ---------------------------------------------------------------- 实例
class InstanceDialog(QDialog):
    """添加 / 编辑实例。"""

    def __init__(self, inst: Instance = None, parent=None,
                 default_python: str = ""):
        super().__init__(parent)
        self.inst = inst or Instance()
        self.setWindowTitle("编辑实例" if inst else "添加实例")
        self.setMinimumWidth(560)

        form = QFormLayout()

        self.ed_name = QLineEdit(self.inst.name)
        self.ed_name.setPlaceholderText("给这个实例起个名字，如：工作机 / 云端")

        self.cb_type = QComboBox()
        self.cb_type.addItem("本地实例（本机 ComfyUI 目录）", TYPE_LOCAL)
        self.cb_type.addItem("远程实例（HTTP 地址）", TYPE_REMOTE)
        self.cb_type.setCurrentIndex(0 if self.inst.type == TYPE_LOCAL else 1)
        self.cb_type.currentIndexChanged.connect(self._toggle_mode)

        self.ed_path = QLineEdit(self.inst.path)
        self.btn_path = QPushButton("浏览…")
        self.btn_path.clicked.connect(self._browse_path)
        self.w_path = QWidget()
        path_box = QHBoxLayout(self.w_path)
        path_box.setContentsMargins(0, 0, 0, 0)
        path_box.addWidget(self.ed_path, 1)
        path_box.addWidget(self.btn_path)

        self.ed_url = QLineEdit(self.inst.url)
        self.ed_url.setPlaceholderText("例如 http://127.0.0.1:8188")
        self.w_url = QWidget()
        url_box = QHBoxLayout(self.w_url)
        url_box.setContentsMargins(0, 0, 0, 0)
        url_box.addWidget(self.ed_url, 1)

        self.ed_python = QLineEdit(self.inst.python)
        self.ed_python.setPlaceholderText("留空则自动识别（便携版/venv/父目录）")
        self.btn_python = QPushButton("浏览…")
        self.btn_python.clicked.connect(self._browse_python)
        self.w_python = QWidget()
        py_box = QHBoxLayout(self.w_python)
        py_box.setContentsMargins(0, 0, 0, 0)
        py_box.addWidget(self.ed_python, 1)
        py_box.addWidget(self.btn_python)

        self.ed_args = QLineEdit(self.inst.launch_args)
        self.ed_args.setPlaceholderText("例如 --disable-metadata --multi-user")

        self.ed_notes = QLineEdit(self.inst.notes)

        form.addRow("名称:", self.ed_name)
        form.addRow("类型:", self.cb_type)
        form.addRow("安装目录:", self.w_path)
        form.addRow("远程地址:", self.w_url)
        form.addRow("Python 程序:", self.w_python)
        form.addRow("实例额外参数:", self.ed_args)
        form.addRow("备注:", self.ed_notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._toggle_mode()

    # ---------- 交互 ----------
    def _toggle_mode(self):
        is_local = self.cb_type.currentData() == TYPE_LOCAL
        self.w_path.setVisible(is_local)
        self.w_url.setVisible(not is_local)
        self.w_python.setVisible(is_local)
        self.ed_args.setVisible(is_local)

    def _browse_path(self):
        start = self.ed_path.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "选择 ComfyUI 安装目录", start)
        if not d:
            return
        self.ed_path.setText(d)
        if not self.ed_name.text().strip():
            self.ed_name.setText(Path(d).name)
        if not self.ed_python.text().strip():
            py = find_python(Path(d))
            if py:
                self.ed_python.setText(py)

    def _browse_python(self):
        start = self.ed_python.text() or ""
        f, _ = QFileDialog.getOpenFileName(self, "选择 Python 可执行文件", start,
                                           "Python (python.exe);;所有文件 (*)")
        if f:
            self.ed_python.setText(f)

    def _validate(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写实例名称")
            return
        typ = self.cb_type.currentData()
        if typ == TYPE_LOCAL:
            p = self.ed_path.text().strip()
            if not p:
                QMessageBox.warning(self, "提示", "请选择 ComfyUI 安装目录")
                return
            if not (Path(p) / "main.py").exists():
                QMessageBox.warning(self, "提示",
                                    f"目录中未找到 main.py，请确认是 ComfyUI 根目录:\n{p}")
                return
            from launcher.instance_scanner import is_comfyui_dir
            if not is_comfyui_dir(Path(p)):
                QMessageBox.warning(
                    self, "提示",
                    f"该目录缺少 ComfyUI 特征目录（comfy / models / custom_nodes），"
                    f"可能不是 ComfyUI 根目录：\n{p}")
                return
            self.inst.path = p
            self.inst.url = ""
        else:
            u = self.ed_url.text().strip()
            if not u:
                QMessageBox.warning(self, "提示", "请填写远程地址")
                return
            self.inst.url = u
            self.inst.path = ""

        self.inst.name = name
        self.inst.type = typ
        self.inst.python = self.ed_python.text().strip()
        self.inst.launch_args = self.ed_args.text().strip()
        self.inst.notes = self.ed_notes.text().strip()
        self.accept()


# ---------------------------------------------------------------- 插件安装
class PluginInstallDialog(QDialog):
    """安装插件：支持 git 克隆或本地文件夹复制。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("安装插件（自定义节点）")
        self.setMinimumWidth(560)

        self.rb_git = QRadioButton("从 Git 仓库克隆")
        self.rb_local = QRadioButton("从本地文件夹复制")
        self.rb_git.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.rb_git)
        group.addButton(self.rb_local)
        self.rb_git.toggled.connect(self._toggle_mode)

        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText("https://github.com/用户/仓库.git")
        self.ed_url.textChanged.connect(self._auto_name)

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("安装后的文件夹名（自动填写，可修改）")

        self.ed_branch = QLineEdit()
        self.ed_branch.setPlaceholderText("留空使用默认分支")

        self.ed_folder = QLineEdit()
        self.btn_folder = QPushButton("浏览…")
        self.btn_folder.clicked.connect(self._browse_folder)
        self.w_folder = QWidget()
        folder_box = QHBoxLayout(self.w_folder)
        folder_box.setContentsMargins(0, 0, 0, 0)
        folder_box.addWidget(self.ed_folder, 1)
        folder_box.addWidget(self.btn_folder)

        self.cb_shallow = QCheckBox("浅克隆（--depth 1，更快）")
        self.cb_shallow.setChecked(True)
        self.cb_deps = QCheckBox("完成后自动安装 requirements.txt 依赖")
        self.cb_deps.setChecked(True)

        form = QFormLayout()
        form.addRow("安装方式:", self.rb_git)
        form.addRow("仓库地址:", self.ed_url)
        form.addRow("分支:", self.ed_branch)
        form.addRow("插件名称:", self.ed_name)
        form.addRow("", self.cb_shallow)
        form.addRow("源文件夹:", self.w_folder)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.cb_deps)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("安装")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._toggle_mode()

    def _toggle_mode(self):
        is_git = self.rb_git.isChecked()
        self.ed_url.setVisible(is_git)
        self.w_folder.setVisible(not is_git)
        self.ed_branch.setEnabled(is_git)
        self.cb_shallow.setEnabled(is_git)
        if not is_git:
            self.cb_shallow.setChecked(False)

    def _auto_name(self, url: str):
        name = (url.strip().rstrip("/").split("/")[-1] or "").replace(".git", "")
        if name and not self.ed_name.text().strip():
            self.ed_name.setText(name)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择插件文件夹",
                                             self.ed_folder.text() or str(Path.home()))
        if d:
            self.ed_folder.setText(d)
            if not self.ed_name.text().strip():
                self.ed_name.setText(Path(d).name)

    def _validate(self):
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写插件名称")
            return
        if self.rb_git.isChecked():
            url = self.ed_url.text().strip()
            if not url:
                QMessageBox.warning(self, "提示", "请填写 Git 仓库地址")
                return
            self.result = {
                "mode": "git", "url": url, "name": name,
                "branch": self.ed_branch.text().strip(),
                "shallow": self.cb_shallow.isChecked(),
                "install_deps": self.cb_deps.isChecked(),
            }
        else:
            folder = self.ed_folder.text().strip()
            if not folder or not Path(folder).is_dir():
                QMessageBox.warning(self, "提示", "请选择有效的源文件夹")
                return
            self.result = {
                "mode": "local", "src": folder, "name": name,
                "install_deps": self.cb_deps.isChecked(),
            }
        self.accept()


# ---------------------------------------------------------------- Torch 安装
class TorchInstallDialog(QDialog):
    """安装 Torch 套件：显示驱动/CUDA 版本，选择 Torch+CUDA 组合。"""

    def __init__(self, driver: str, cuda: str, parent=None):
        super().__init__(parent)
        self.result = None
        self.setWindowTitle("安装 Torch 套件")
        self.setMinimumWidth(560)

        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLabel
        from launcher.kernel_manager import TORCH_CHOICES

        v = QVBoxLayout(self)
        v.setSpacing(10)

        # CUDA 版本检测
        title = QLabel("CUDA 版本检测")
        title.setStyleSheet("font-weight: 600;")
        v.addWidget(title)
        driver_txt = driver or "未知"
        cuda_txt = cuda or "未知"
        info = QLabel(f"驱动版本: {driver_txt}　|　CUDA 版本: {cuda_txt}")
        info.setProperty("dim", True)
        v.addWidget(info)

        # 选择 Torch 版本
        sel = QLabel("选择 Torch 版本")
        sel.setStyleSheet("font-weight: 600; margin-top: 6px;")
        v.addWidget(sel)
        tip = QLabel("请选择要安装的 Torch 版本和 CUDA 版本:")
        tip.setProperty("dim", True)
        v.addWidget(tip)

        # 下拉框：默认按驱动过滤（≤ 驱动 CUDA），勾选后显示全部
        self.cb_torch = QComboBox()
        self._all_choices = TORCH_CHOICES
        self._driver_cuda = cuda
        self._fill(show_all=False)
        v.addWidget(self.cb_torch)

        self.cb_show_all = QCheckBox("显示全部版本（含需要更高驱动 CUDA 的版本）")
        self.cb_show_all.setProperty("dim", True)
        self.cb_show_all.toggled.connect(self._on_show_all)
        v.addWidget(self.cb_show_all)

        warn = QLabel("请根据自身情况选择安装")
        warn.setProperty("dim", True)
        v.addWidget(warn)

        # 按钮
        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_install = QPushButton("安装")
        btn_install.setObjectName("primary")
        btn_install.setFixedHeight(32)
        btn_install.setMinimumWidth(90)
        btn_install.clicked.connect(self._ok)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_install)
        btns.addWidget(btn_cancel)
        v.addLayout(btns)

    # ------------------------------------------------------------ 逻辑
    def _cu_num(self, suffix) -> int:
        m = re.search(r"cu(\d+)", suffix or "")
        return int(m.group(1)) if m else 0

    @staticmethod
    def _torch_key(label: str):
        """从显示名解析 torch 版本 → (主,次,修订) 元组；失败返回 (0,0,0)。"""
        m = re.search(r"v(\d+)\.(\d+)(?:\.(\d+))?", label)
        if not m:
            return (0, 0, 0)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))

    def _fill(self, show_all: bool):
        self.cb_torch.blockSignals(True)
        self.cb_torch.clear()
        if show_all or not self._driver_cuda:
            choices = self._all_choices
        else:
            # 驱动 CUDA 13.0 → 显示 cu130 及以下；cu132 需要驱动 13.2+
            max_cu = self._cu_num(f"cu{self._driver_cuda.replace('.', '')}")
            choices = [(l, s) for l, s in self._all_choices
                       if self._cu_num(s) <= max_cu]
        # 按 Torch 版本从新到旧，同版本内按 CUDA 从新到旧
        choices.sort(
            key=lambda ls: (self._torch_key(ls[0]), self._cu_num(ls[1])),
            reverse=True)
        for label, suffix in choices:
            self.cb_torch.addItem(label, suffix)
        self._preselect()
        self.cb_torch.blockSignals(False)

    def _on_show_all(self, checked):
        self._fill(show_all=checked)

    def _preselect(self):
        """按驱动 CUDA 版本默认选中匹配的最新项。"""
        if not self._driver_cuda:
            # 无 NVIDIA：默认选第一个
            if self.cb_torch.count():
                self.cb_torch.setCurrentIndex(0)
            return
        try:
            target = self._cu_num(f"cu{self._driver_cuda.replace('.', '')}")
        except ValueError:
            target = 0
        best = 0
        for i in range(self.cb_torch.count()):
            cu = self._cu_num(self.cb_torch.itemData(i))
            if cu <= target and cu >= best:
                best = cu
                self.cb_torch.setCurrentIndex(i)

    def _ok(self):
        label = self.cb_torch.currentText()
        suffix = self.cb_torch.currentData()
        m = re.search(r"v(\d+\.\d+\.\d+)", label)
        self.result = {
            "label": label,
            "suffix": suffix,
            "version": m.group(1) if m else "",
        }
        self.accept()


# ---------------------------------------------------------------- Wheel 安装选择
class WheelInstallDialog(QDialog):
    """选择要安装的 Windows 轮子：自动预选匹配项，未匹配到也可手动改选。

    plan: kernel_manager.wheel_install_plan() 的返回，含
          title / torch / cu / py / items:[(label, url)] / matched:下标或None。
    """

    def __init__(self, plan: dict, parent=None):
        super().__init__(parent)
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLabel

        self.result = None
        self.setWindowTitle(plan.get("title", "安装内核组件"))
        self.setMinimumWidth(680)
        v = QVBoxLayout(self)
        v.setSpacing(10)

        torch_txt = plan.get("torch") or "未检测到"
        cu_txt = plan.get("cu") or ""
        py_txt = plan.get("py") or "?"
        info = QLabel(
            f"已装 torch：{torch_txt} {f'({cu_txt})' if cu_txt else ''}　|　"
            f"Python {py_txt[:1]}.{py_txt[1:] if len(py_txt) > 1 else '?'}")
        info.setStyleSheet("font-weight: 600;")
        v.addWidget(info)

        items = plan.get("items") or []
        matched = plan.get("matched")
        self._matched = matched if matched is not None else -1
        if not items:
            tip = QLabel("未获取到可用轮子（网络异常或没有匹配项），请稍后重试。")
            tip.setProperty("dim", True)
            v.addWidget(tip)
        else:
            if matched is not None:
                tip = QLabel(
                    f"✔ 已自动匹配（第 {matched + 1} 项）；如需其他版本可手动改选，"
                    "安装后会验证并自动回滚不兼容项。")
                tip.setProperty("dim", True)
            else:
                tip = QLabel(
                    "⚠ 未找到精确匹配的轮子，以下为全部可用选项。"
                    "选错可能导致 CUDA 不兼容——安装后会自动验证，验证失败将自动回滚。")
                tip.setProperty("dim", True)
            v.addWidget(tip)
            self.cb = QComboBox()
            self.cb.setMinimumHeight(32)
            for label, url in items:
                self.cb.addItem(label, url)
                # 完整 wheel 文件名放到悬停提示里，避免列表被长名刷屏
                fname = url.split("?")[0].split("/")[-1]
                if fname:
                    self.cb.setItemData(self.cb.count() - 1, fname,
                                        Qt.ToolTipRole)
            if matched is not None and 0 <= matched < len(items):
                self.cb.setCurrentIndex(matched)
            v.addWidget(self.cb)
            v.addSpacing(4)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_install = QPushButton("安装所选")
        btn_install.setObjectName("primary")
        btn_install.setFixedHeight(32)
        btn_install.setMinimumWidth(100)
        btn_install.setEnabled(bool(items))
        btn_install.clicked.connect(self._ok)
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_install)
        btns.addWidget(btn_cancel)
        v.addLayout(btns)

    def _ok(self):
        # 用户改选了非自动匹配项：提示可能不兼容，确认后仍可继续
        # （安装后会自动验证，验证失败自动回滚）
        if self._matched >= 0 and self.cb.currentIndex() != self._matched:
            ret = QMessageBox.question(
                self, "确认安装",
                "你选择的是非自动匹配项，可能与该实例的 torch 不兼容。\n\n"
                "安装后会进行验证，验证失败将自动回滚，不会破坏原有版本。\n\n"
                "仍要继续吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.result = {
            "label": self.cb.currentText(),
            "url": self.cb.currentData(),
        }
        self.accept()
