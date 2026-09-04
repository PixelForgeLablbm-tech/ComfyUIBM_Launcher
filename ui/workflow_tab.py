# -*- coding: utf-8 -*-
"""工作流识别页签：放入 ComfyUI 工作流 → 识别已安装 / 未安装的插件。

未安装插件给出插件名（仓库名），可一键复制，到「插件管理 → 插件搜索」
搜索后安装。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from launcher import workflow_scan


class WorkflowTab(QWidget):
    """工作流识别：文件 → 节点 → 已装/未装插件。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._last_path = ""
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(10)

        # 文件选择
        top = QGroupBox("工作流识别")
        tv = QVBoxLayout(top)
        tip = QLabel("放入 / 选择 ComfyUI 工作流文件（json），识别它用到的插件，"
                     "区分已安装与未安装；未安装的可复制插件名，"
                     "到「插件管理 → 插件搜索」搜索安装。")
        tip.setProperty("dim", True)
        tip.setWordWrap(True)
        tv.addWidget(tip)
        row = QHBoxLayout()
        self.btn_pick = QPushButton("选择工作流文件…")
        self.btn_pick.setObjectName("primary")
        self.btn_pick.setFixedHeight(32)
        self.btn_pick.clicked.connect(self.pick_file)
        row.addWidget(self.btn_pick)
        self.lb_file = QLabel("未选择文件（也可直接把 json 拖进来）")
        self.lb_file.setProperty("dim", True)
        row.addWidget(self.lb_file, 1)
        tv.addLayout(row)
        lay.addWidget(top)

        # 结果
        card = QGroupBox("识别结果")
        cv = QVBoxLayout(card)

        head = QHBoxLayout()
        head.addWidget(QLabel("<b>已安装</b>"))
        head.addStretch(1)
        self.lb_summary = QLabel("")
        self.lb_summary.setProperty("dim", True)
        head.addWidget(self.lb_summary)
        cv.addLayout(head)

        self.list_installed = QListWidget()
        self.list_installed.setMaximumHeight(170)
        cv.addWidget(self.list_installed)

        miss_head = QHBoxLayout()
        miss_head.addWidget(QLabel("<b>未安装（可复制插件名去插件管理搜索）</b>"))
        miss_head.addStretch(1)
        btn_copy_all = QPushButton("复制全部未安装插件名")
        btn_copy_all.setObjectName("ghost")
        btn_copy_all.setFixedHeight(28)
        btn_copy_all.clicked.connect(self._copy_all_missing)
        self.btn_copy_all = btn_copy_all
        miss_head.addWidget(btn_copy_all)
        cv.addLayout(miss_head)

        self.list_missing = QListWidget()
        cv.addWidget(self.list_missing, 1)

        lay.addWidget(card, 1)

        # 识别不到的节点提示
        self.lb_unmapped = QLabel("")
        self.lb_unmapped.setProperty("dim", True)
        self.lb_unmapped.setWordWrap(True)
        lay.addWidget(self.lb_unmapped)

        self.setAcceptDrops(True)

    # ------------------------------------------------------------ 拖拽
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and p.lower().endswith(".json"):
                self.analyze_file(p)
                return

    # ------------------------------------------------------------ 逻辑
    def pick_file(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择 ComfyUI 工作流", "", "工作流 (*.json);;所有文件 (*)")
        if f:
            self.analyze_file(f)

    def analyze_file(self, path):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(
                self, "提示", "请先在「实例管理」中选择一个本地实例，"
                             "才能识别哪些插件已安装")
            return
        self._last_path = path
        self.lb_file.setText(path)
        self.list_installed.clear()
        self.list_missing.clear()
        self.lb_summary.setText("识别中…")
        self.lb_unmapped.setText("")
        self.btn_copy_all.setEnabled(False)
        self.btn_pick.setEnabled(False)

        def work(report):
            report("正在解析工作流并匹配插件…")
            return workflow_scan.analyze_workflow(inst.path, path)

        def done(res):
            self.btn_pick.setEnabled(True)
            self.btn_copy_all.setEnabled(bool(res["missing"]))
            self.lb_summary.setText(
                f"共 {len(res['missing']) + len(res['installed'])} 个相关插件："
                f"已安装 {len(res['installed'])} · "
                f"未安装 {len(res['missing'])}")
            for it in res["installed"]:
                self._add_item(self.list_installed, it["name"], it["nodes"],
                               installed=True)
            for it in res["missing"]:
                self._add_item(self.list_missing, it["name"], it["nodes"],
                               installed=False, repo=it["repo"])
            if res["unmapped"]:
                shown = "、".join(res["unmapped"][:8])
                more = f" 等 {len(res['unmapped'])} 个" \
                    if len(res["unmapped"]) > 8 else ""
                self.lb_unmapped.setText(
                    f"未识别节点（多为 ComfyUI 内置节点，无需安装）：{shown}{more}")
            if not res["missing"] and not res["installed"]:
                self.lb_summary.setText("工作流里没有识别到第三方插件节点")
            self.win.log(f"工作流识别完成：{path}")

        def fail(err):
            self.btn_pick.setEnabled(True)
            self.lb_summary.setText("")
            QMessageBox.warning(self, "识别失败", str(err))

        self.win.tasks.start(
            work, on_done=done, on_error=fail,
            warn_on_close=False)

    def _add_item(self, lst, name, nodes, installed, repo=""):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 3, 8, 3)
        rl.setSpacing(8)
        if not installed:
            btn = QPushButton("复制")
            btn.setObjectName("ghost")
            btn.setFixedHeight(24)
            btn.setFixedWidth(52)
            btn.clicked.connect(
                lambda _=False, n=name: self._copy_text(n))
            rl.addWidget(btn)
        nm = QLabel(name)
        nm.setTextInteractionFlags(Qt.TextSelectableByMouse)
        nm.setStyleSheet("font-weight: 600;")
        rl.addWidget(nm)
        rl.addStretch(1)
        if nodes:
            d = QLabel(f"节点：{', '.join(nodes[:4])}"
                       + (" …" if len(nodes) > 4 else ""))
            d.setStyleSheet("color: #8b96a8; font-size: 11.5px;")
            d.setTextInteractionFlags(Qt.TextSelectableByMouse)
            rl.addWidget(d)
        item = QListWidgetItem(lst)
        item.setSizeHint(row.sizeHint())
        lst.addItem(item)
        lst.setItemWidget(item, row)
        lst.setToolTip(repo or name)

    # ------------------------------------------------------------ 复制
    def _copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.win.sb(f"已复制：{text}")

    def _copy_all_missing(self):
        names = []
        for i in range(self.list_missing.count()):
            item = self.list_missing.item(i)
            w = self.list_missing.itemWidget(item)
            if w:
                lbl = w.findChild(QLabel)
                if lbl and lbl.text().strip():
                    names.append(lbl.text().strip())
        if names:
            # 每行一个插件名，方便逐条粘贴搜索
            QApplication.clipboard().setText("\n".join(names))
            self.win.sb(f"已复制 {len(names)} 个未安装插件名")
            QMessageBox.information(
                self, "已复制",
                f"已复制 {len(names)} 个插件名：\n\n" + "\n".join(names) +
                "\n\n粘贴到「插件管理 → 插件搜索」逐个搜索安装。")

    # ------------------------------------------------------------ 数据
    def reload(self):
        """页面切换时调用（预留）。"""
        if not self._last_path:
            return
        # 重进页面时自动重新识别一次（插件可能装好了）
        self.analyze_file(self._last_path)
