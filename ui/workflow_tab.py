# -*- coding: utf-8 -*-
"""工作流识别页：选择工作流，识别所需插件，并对照本地安装状态。"""
import os

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
    QSplitter, QVBoxLayout, QWidget,
)

from launcher import workflow_scan


class _ElidedLabel(QLabel):
    """单行文字在空间不足时显示省略号，完整内容保留在悬停提示中。"""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(0, self.contentsRect().width())
        QLabel.setText(self, self.fontMetrics().elidedText(
            self._full_text, Qt.ElideRight, width))


class WorkflowTab(QWidget):
    """工作流文件 → 插件识别结果，未安装项优先提供下一步操作。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._last_path = ""
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 10)
        lay.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("工作流识别")
        title.setObjectName("workflowPageTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.lb_result_state = QLabel("等待选择工作流")
        self.lb_result_state.setObjectName("workflowResultState")
        self.lb_result_state.setProperty("state", "idle")
        title_row.addWidget(self.lb_result_state)
        lay.addLayout(title_row)

        # 既是文件选择区也是拖放目标；完整路径放在提示中，不挤压操作按钮。
        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("workflowDropZone")
        self.drop_zone.setProperty("dragActive", False)
        drop_lay = QVBoxLayout(self.drop_zone)
        drop_lay.setContentsMargins(18, 15, 18, 15)
        drop_lay.setSpacing(8)

        drop_title = QLabel("拖入 ComfyUI 工作流 JSON 文件")
        drop_title.setObjectName("workflowDropTitle")
        drop_lay.addWidget(drop_title)
        drop_tip = QLabel(
            "识别工作流使用的第三方节点，并与当前本地实例的 custom_nodes 对照。")
        drop_tip.setProperty("dim", True)
        drop_lay.addWidget(drop_tip)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.lb_file = QLabel("尚未选择文件 · 也可以直接拖入 .json")
        self.lb_file.setObjectName("workflowFileName")
        self.lb_file.setProperty("dim", True)
        self.lb_file.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lb_file.setToolTip("尚未选择文件")
        file_row.addWidget(self.lb_file, 1)

        self.btn_reanalyze = QPushButton("重新识别")
        self.btn_reanalyze.setObjectName("ghost")
        self.btn_reanalyze.setFixedHeight(32)
        self.btn_reanalyze.setEnabled(False)
        self.btn_reanalyze.clicked.connect(self._reanalyze)
        file_row.addWidget(self.btn_reanalyze)

        self.btn_pick = QPushButton("选择工作流文件…")
        self.btn_pick.setObjectName("primary")
        self.btn_pick.setFixedHeight(32)
        self.btn_pick.clicked.connect(self.pick_file)
        file_row.addWidget(self.btn_pick)
        drop_lay.addLayout(file_row)
        lay.addWidget(self.drop_zone)

        # 两栏结果让“需要处理”和“已经就绪”可直接对照；分隔条可调比例。
        result_box = QGroupBox("识别结果")
        result_lay = QVBoxLayout(result_box)
        result_lay.setContentsMargins(12, 14, 12, 12)
        result_lay.setSpacing(10)

        summary = QHBoxLayout()
        summary.setSpacing(8)
        summary.addWidget(QLabel("插件状态"))
        summary.addStretch(1)
        self.lb_missing_count = QLabel("需要安装 0")
        self.lb_missing_count.setObjectName("workflowMissingBadge")
        summary.addWidget(self.lb_missing_count)
        self.lb_installed_count = QLabel("已安装 0")
        self.lb_installed_count.setObjectName("workflowInstalledBadge")
        summary.addWidget(self.lb_installed_count)
        result_lay.addLayout(summary)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        missing_pane, self.list_missing = self._make_result_pane(
            "需要安装", "复制插件名后，到“插件管理”搜索安装", missing=True)
        installed_pane, self.list_installed = self._make_result_pane(
            "已安装", "当前实例已能提供这些工作流节点", missing=False)
        splitter.addWidget(missing_pane)
        splitter.addWidget(installed_pane)
        splitter.setSizes([520, 480])
        result_lay.addWidget(splitter, 1)
        lay.addWidget(result_box, 1)

        self.unmapped_box = QFrame()
        self.unmapped_box.setObjectName("workflowHint")
        hint_lay = QHBoxLayout(self.unmapped_box)
        hint_lay.setContentsMargins(12, 8, 12, 8)
        hint_lay.setSpacing(8)
        hint_title = QLabel("未映射节点")
        hint_title.setObjectName("workflowHintTitle")
        hint_lay.addWidget(hint_title, 0, Qt.AlignTop)
        self.lb_unmapped = QLabel()
        self.lb_unmapped.setProperty("dim", True)
        self.lb_unmapped.setWordWrap(True)
        hint_lay.addWidget(self.lb_unmapped, 1)
        self.unmapped_box.setVisible(False)
        lay.addWidget(self.unmapped_box)

        self._set_counts(0, 0)
        self._show_empty(self.list_missing, "选择工作流后，会在这里列出需要安装的插件")
        self._show_empty(self.list_installed, "识别完成后，会在这里显示已安装的插件")
        self.setAcceptDrops(True)

    def _make_result_pane(self, title, subtitle, missing):
        pane = QFrame()
        pane.setObjectName("workflowMissingPane" if missing else "workflowInstalledPane")
        pane_lay = QVBoxLayout(pane)
        pane_lay.setContentsMargins(10, 10, 10, 10)
        pane_lay.setSpacing(7)

        head = QHBoxLayout()
        head.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("workflowPaneTitle")
        head.addWidget(heading)
        head.addStretch(1)
        if missing:
            self.btn_copy_all = QPushButton("复制全部")
            self.btn_copy_all.setObjectName("ghost")
            self.btn_copy_all.setFixedHeight(28)
            self.btn_copy_all.setEnabled(False)
            self.btn_copy_all.clicked.connect(self._copy_all_missing)
            head.addWidget(self.btn_copy_all)
        pane_lay.addLayout(head)

        tip = QLabel(subtitle)
        tip.setProperty("dim", True)
        tip.setObjectName("workflowPaneTip")
        pane_lay.addWidget(tip)

        lst = QListWidget()
        lst.setObjectName("workflowMissingList" if missing else "workflowInstalledList")
        lst.setSpacing(6)
        lst.setSelectionMode(QListWidget.NoSelection)
        pane_lay.addWidget(lst, 1)
        return pane, lst

    @staticmethod
    def _show_empty(lst, text):
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setTextAlignment(Qt.AlignCenter)
        item.setSizeHint(QSize(0, 56))
        lst.addItem(item)

    def _set_counts(self, missing, installed):
        self.lb_missing_count.setText(f"需要安装 {missing}")
        self.lb_installed_count.setText(f"已安装 {installed}")

    def _set_status(self, text, state):
        self.lb_result_state.setText(text)
        self.lb_result_state.setProperty("state", state)
        self.lb_result_state.style().unpolish(self.lb_result_state)
        self.lb_result_state.style().polish(self.lb_result_state)

    def _set_drag_active(self, active):
        self.drop_zone.setProperty("dragActive", active)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    # ------------------------------------------------------------ 拖拽
    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(url.toLocalFile().lower().endswith(".json") for url in urls):
            self._set_drag_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event):
        self._set_drag_active(False)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(".json"):
                self.analyze_file(path)
                event.acceptProposedAction()
                return

    # ------------------------------------------------------------ 逻辑
    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 ComfyUI 工作流", "", "工作流 (*.json);;所有文件 (*)")
        if path:
            self.analyze_file(path)

    def _reanalyze(self):
        if self._last_path:
            self.analyze_file(self._last_path)

    def analyze_file(self, path):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.information(
                self, "提示", "请先在“实例管理”中选择一个本地实例，"
                             "才能识别哪些插件已安装")
            return

        self._last_path = path
        filename = os.path.basename(path)
        self.lb_file.setText(f"已选择：{filename}")
        self.lb_file.setProperty("dim", False)
        self.lb_file.setToolTip(path)
        self.list_installed.clear()
        self.list_missing.clear()
        self._show_empty(self.list_missing, "正在识别工作流…")
        self._show_empty(self.list_installed, "正在识别工作流…")
        self._set_counts(0, 0)
        self.lb_unmapped.clear()
        self.unmapped_box.setVisible(False)
        self._set_status("正在识别…", "busy")
        self.btn_copy_all.setEnabled(False)
        self.btn_pick.setEnabled(False)
        self.btn_reanalyze.setEnabled(False)

        def work(report):
            report("正在解析工作流并匹配插件…")
            return workflow_scan.analyze_workflow(inst.path, path)

        def done(result):
            missing = result["missing"]
            installed = result["installed"]
            self.btn_pick.setEnabled(True)
            self.btn_reanalyze.setEnabled(True)
            self.btn_copy_all.setEnabled(bool(missing))
            self.list_installed.clear()
            self.list_missing.clear()
            self._set_counts(len(missing), len(installed))

            for entry in missing:
                self._add_item(self.list_missing, entry["name"], entry["nodes"],
                               installed=False, repo=entry["repo"])
            for entry in installed:
                self._add_item(self.list_installed, entry["name"], entry["nodes"],
                               installed=True)
            if not missing:
                self._show_empty(self.list_missing, "这个工作流没有发现需要安装的插件")
            if not installed:
                self._show_empty(self.list_installed, "没有匹配到已安装的第三方插件")

            total = len(missing) + len(installed)
            self._set_status(f"识别完成 · {total} 个相关插件" if total else
                             "未发现第三方插件", "success" if total else "idle")

            if result["unmapped"]:
                shown = "、".join(result["unmapped"][:8])
                more = (f" 等 {len(result['unmapped'])} 个"
                        if len(result["unmapped"]) > 8 else "")
                self.lb_unmapped.setText(
                    "以下节点没有映射到第三方插件，通常是 ComfyUI 内置节点，"
                    f"无需安装：{shown}{more}")
                self.unmapped_box.setVisible(True)
            self.win.log(f"工作流识别完成：{path}")

        def fail(err):
            self.btn_pick.setEnabled(True)
            self.btn_reanalyze.setEnabled(bool(self._last_path))
            self._set_status("识别失败", "error")
            QMessageBox.warning(self, "识别失败", str(err))

        self.win.tasks.start(work, on_done=done, on_error=fail,
                             warn_on_close=False)

    def _add_item(self, lst, name, nodes, installed, repo=""):
        row = QFrame()
        row.setObjectName("workflowInstalledItem" if installed else "workflowMissingItem")
        # 两行文字 + 上下边距至少需要 62px；否则 QListWidget 会把第二行裁掉。
        row.setFixedHeight(62)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 8, 8, 8)
        row_lay.setSpacing(10)

        text_lay = QVBoxLayout()
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(3)
        name_label = QLabel(name)
        name_label.setObjectName("workflowPluginName")
        name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        name_label.setToolTip(repo or name)
        text_lay.addWidget(name_label)
        node_text = "涉及节点：" + "、".join(nodes[:4])
        if len(nodes) > 4:
            node_text += f" 等 {len(nodes)} 个"
        nodes_label = _ElidedLabel(node_text)
        nodes_label.setObjectName("workflowPluginNodes")
        nodes_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        nodes_label.setToolTip("\n".join(nodes))
        text_lay.addWidget(nodes_label)
        row_lay.addLayout(text_lay, 1)

        if not installed:
            copy_btn = QPushButton("复制名称")
            copy_btn.setObjectName("ghost")
            # 四个中文字符 + 全局按钮左右内边距，76px 会裁字。
            copy_btn.setFixedSize(96, 28)
            copy_btn.setToolTip("复制插件名，用于“插件管理”中搜索")
            copy_btn.clicked.connect(lambda _=False, value=name: self._copy_text(value))
            row_lay.addWidget(copy_btn)

        item = QListWidgetItem()
        item.setData(Qt.UserRole, name)
        item.setToolTip(repo or name)
        item.setSizeHint(QSize(0, 62))
        lst.addItem(item)
        lst.setItemWidget(item, row)

    # ------------------------------------------------------------ 复制
    def _copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.win.sb(f"已复制：{text}")

    def _copy_all_missing(self):
        names = [self.list_missing.item(i).data(Qt.UserRole)
                 for i in range(self.list_missing.count())]
        names = [name for name in names if name]
        if not names:
            return
        QApplication.clipboard().setText("\n".join(names))
        self.win.sb(f"已复制 {len(names)} 个未安装插件名")
        QMessageBox.information(
            self, "已复制",
            f"已复制 {len(names)} 个插件名：\n\n" + "\n".join(names) +
            "\n\n粘贴到“插件管理 → 插件搜索”逐个搜索安装。")

    # ------------------------------------------------------------ 数据
    def reload(self):
        """页面切换时重跑最近一次识别，反映新安装的插件。"""
        if self._last_path:
            self.analyze_file(self._last_path)
