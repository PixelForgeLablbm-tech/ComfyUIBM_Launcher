# -*- coding: utf-8 -*-
"""更新维护页签：版本列表（tags/分支）/ 更新 / 回滚 / 依赖安装。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from launcher import updater


def _badge(text, color, bg):
    lb = QLabel(text)
    lb.setStyleSheet(
        f"padding: 1px 7px; border-radius: 8px; font-size: 11px; "
        f"background: {bg}; color: {color};")
    return lb


class VersionItem(QWidget):
    """版本列表项：radio 圆点 + 名称 + 徽标 + 日期 + 提交。"""

    def __init__(self, name, commit, date=None, is_current=False,
                 is_latest=False, selected=False, parent=None):
        super().__init__(parent)
        self.name = name
        # 显式透明：WA_TranslucentBackground 对列表项 widget 不可靠
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(8)

        self.dot = QLabel()
        self.dot.setFixedWidth(14)
        self.dot.setStyleSheet("background: transparent;")
        lay.addWidget(self.dot)

        nm = QLabel(name)
        nm.setStyleSheet("background: transparent; font-weight: 600;")
        lay.addWidget(nm)

        if is_current:
            lay.addWidget(_badge("当前", "#34d399", "rgba(52,211,153,0.16)"))
        elif is_latest:
            lay.addWidget(_badge("最新", "#c4b5fd", "rgba(124,92,255,0.20)"))

        lay.addStretch(1)

        if date:
            d = QLabel(date)
            d.setStyleSheet("background: transparent; color: #8b96a8; font-size: 11.5px;")
            lay.addWidget(d)

        c = QLabel(commit)
        c.setStyleSheet(
            "background: transparent; color: #8fa2b8; font-size: 11px; "
            "font-family: Consolas, monospace;")
        lay.addWidget(c)

        self.set_selected(selected)

    def set_selected(self, sel: bool):
        self.dot.setText("●" if sel else "○")
        self.dot.setStyleSheet(
            "color: #7c5cff; font-size: 13px;" if sel
            else "color: #3a4560; font-size: 13px;")


class VersionList(QListWidget):
    """版本列表：每项使用 VersionItem 渲染。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QAbstractItemView
        self.setObjectName("verList")
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._entries = []   # [(item, widget, name)]

    def set_versions(self, versions, selected, latest_tag):
        self.clear()
        self._entries = []
        for v in versions:
            name = v["name"]
            widget = VersionItem(
                name, v.get("commit", ""), v.get("date"),
                is_current=bool(v.get("is_current")),
                is_latest=(name == latest_tag),
                selected=(name == selected),
            )
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.addItem(item)
            self.setItemWidget(item, widget)
            self._entries.append((item, widget, name))

    def select_name(self, name):
        for item, _w, n in self._entries:
            if n == name:
                self.setCurrentItem(item)
                return

    def refresh_dots(self, selected):
        for _item, widget, name in self._entries:
            widget.set_selected(name == selected)


class UpdateTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._info = None
        self._selected = ""
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(14)

        # ---------------- 左栏：版本列表占满 GitHub 加速卡片释放的高度 ----------------
        left = QWidget()
        left.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # 卡片1：当前版本
        card_ver = QGroupBox("ComfyUI 版本")
        vbox = QVBoxLayout(card_ver)
        row = QHBoxLayout()
        self.lb_version = QLabel("—")
        self.lb_version.setProperty("accent", True)
        row.addWidget(self.lb_version)
        row.addStretch(1)
        # 「刷新版本」：只刷新左上角当前版本显示（本地 git 读取），普通样式
        self.btn_version_refresh = QPushButton("刷新版本")
        self.btn_version_refresh.setFixedSize(100, 32)
        self.btn_version_refresh.clicked.connect(
            lambda: self._load_version_text(feedback=True))
        row.addWidget(self.btn_version_refresh)
        self.btn_refresh = QPushButton("刷新版本列表")
        self.btn_refresh.setObjectName("primary")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self.refresh_versions)
        row.addWidget(self.btn_refresh)
        vbox.addLayout(row)
        tip = QLabel("需联网获取；失败时请检查网络 / 设置中的代理 / GitHub 加速。")
        tip.setProperty("dim", True)
        tip.setWordWrap(True)
        vbox.addWidget(tip)
        lay.addWidget(card_ver)

        # 卡片2：版本列表 + 操作
        card_list = QGroupBox("版本列表")
        cv = QVBoxLayout(card_list)
        cv.setSpacing(6)
        lb_tags = QLabel("发布版（Tags）")
        lb_tags.setProperty("dim", True)
        cv.addWidget(lb_tags)
        self.list_tags = VersionList()
        self.list_tags.currentItemChanged.connect(self._on_list_changed)
        cv.addWidget(self.list_tags, 1)

        ops = QHBoxLayout()
        self.btn_update_sel = QPushButton("更新到所选版本")
        self.btn_update_sel.setObjectName("primary")
        self.btn_update_sel.setFixedHeight(32)
        self.btn_update_sel.clicked.connect(self.update_selected)
        self.btn_req = QPushButton("安装 requirements")
        self.btn_req.setFixedHeight(32)
        self.btn_req.setToolTip(
            "手动执行 pip install -r requirements.txt（强制重装依赖）\n"
            "用于：更新后启动报错缺模块 / 上次依赖安装失败 / 想强制重装")
        self.btn_req.clicked.connect(self.install_requirements)
        for b in (self.btn_update_sel, self.btn_req):
            ops.addWidget(b)
        ops.addStretch(1)
        cv.addLayout(ops)

        self.lb_selected = QLabel("未选择版本")
        self.lb_selected.setProperty("dim", True)
        cv.addWidget(self.lb_selected)

        tips = QLabel(
            "· 选择旧版本即可回滚；更新前会自动暂存本地改动，更新后恢复\n"
            "· 建议更新前先停止正在运行的 ComfyUI\n"
            "· 更新/回滚会自动对比新旧版本依赖，有变化才自动安装；\n"
            "  如遇依赖问题或想强制重装，点上方「安装 requirements」")
        tips.setProperty("dim", True)
        tips.setWordWrap(True)
        tips.setStyleSheet("font-size: 12px; line-height: 1.7;")
        cv.addWidget(tips)
        lay.addWidget(card_list, 1)

        root.addWidget(left, 3)

        # ---------------- 右栏：操作日志 ----------------
        card_log = QGroupBox("操作日志")
        lv = QVBoxLayout(card_log)
        self.op_log = QPlainTextEdit()
        self.op_log.setReadOnly(True)
        self.op_log.setMaximumBlockCount(3000)
        self.op_log.setPlaceholderText("点击更新按钮后，输出将显示在这里…")
        lv.addWidget(self.op_log, 1)
        head = QHBoxLayout()
        t = QLabel("实时输出")
        t.setProperty("dim", True)
        head.addWidget(t)
        head.addStretch(1)
        btn_clear = QPushButton("清空")
        btn_clear.setObjectName("ghost")
        btn_clear.setFixedHeight(32)
        btn_clear.clicked.connect(self.op_log.clear)
        head.addWidget(btn_clear)
        lv.addLayout(head)
        root.addWidget(card_log, 2)

    # ------------------------------------------------------------ 数据
    def reload(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            self.setEnabled(False)
            self.lb_version.setText("请先在「实例管理」中选择一个本地实例")
            self.list_tags.clear()
            return
        self.setEnabled(True)
        self._info = None
        self._selected = ""
        self._load_version_text()
    def _load_version_text(self, feedback=False):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            if feedback:
                self.win.sb("未选择本地实例")
            return
        if feedback:
            self.btn_version_refresh.setEnabled(False)
            self.btn_version_refresh.setText("刷新中…")

        def done(v):
            self.lb_version.setText(v)
            if feedback:
                self.btn_version_refresh.setEnabled(True)
                self.btn_version_refresh.setText("刷新版本")
                self.win.sb("当前版本已刷新")

        def fail(e):
            if feedback:
                self.btn_version_refresh.setEnabled(True)
                self.btn_version_refresh.setText("刷新版本")
                self.win.sb(f"刷新版本失败：{e}")

        self.win.tasks.start(
            lambda report, i=inst: updater.version(i.path),
            on_done=done,
            on_error=fail,
        )

    # ------------------------------------------------------------ 版本列表
    def refresh_versions(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            return
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("查询中…")
        self.op_log.clear()
        self.op_log.appendPlainText("正在查询远端版本列表…")
        # 用户主动刷新：绕过 60 秒缓存，确保「当前」标记等为最新
        updater._VERSION_CACHE.update(key=None, at=0.0, info=None)
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, i=inst: updater.list_versions(i, mirrors, report),
            on_progress=lambda m: self._op(m),
            on_done=self._on_versions,
            on_error=lambda e: self._versions_error(e),
        )

    def _op(self, msg):
        self.op_log.appendPlainText(msg)

    def _on_versions(self, info):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("刷新版本列表")
        self._info = info
        self._selected = info.get("latest_tag") or ""
        # 同步更新左上角当前版本显示（刷新后版本应是最新）
        if info.get("current"):
            self.lb_version.setText(info["current"])
        self._fill_lists()
        self._update_selected_label()
        if not info.get("tags"):
            self._op("未获取到版本列表。请检查：网络连接 / 设置页的代理 / GitHub 加速。")

    def _versions_error(self, err):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("刷新版本列表")
        self._op(f"⚠ {err}")
        self._op("提示：确认本机可访问 GitHub；若需代理请到「设置」启用并填写地址，"
                 "或开启 GitHub 加速后重试。")
        QMessageBox.critical(self, "查询失败",
                             f"{err}\n\n提示：\n· 确认本机网络可访问 GitHub\n"
                             "· 需要代理时请到「设置」启用代理并填写地址\n"
                             "· 可尝试开启 GitHub 加速后重试")

    def _fill_lists(self):
        info = self._info or {}
        latest = info.get("latest_tag")
        tags = info.get("tags", [])
        if not tags:
            self._add_empty(self.list_tags, "未获取到发布版列表")
        else:
            self.list_tags.set_versions(tags, self._selected, latest)

    def _add_empty(self, lst: QListWidget, text: str):
        lst.clear()
        item = QListWidgetItem(text)
        from PyQt5.QtGui import QColor
        item.setForeground(QColor("#8b96a8"))
        item.setFlags(Qt.ItemIsEnabled)
        lst.addItem(item)

    def _on_list_changed(self, current, _prev):
        if current is None:
            return
        w = self.list_tags.itemWidget(current)
        if w is None:
            return
        self._selected = w.name
        self.list_tags.refresh_dots(self._selected)
        self._update_selected_label()

    def _update_selected_label(self):
        info = self._info or {}
        if self._selected:
            tag = "（最新发布版）" if self._selected == info.get("latest_tag") else ""
            self.lb_selected.setText(f"已选择：{self._selected} {tag}")
        else:
            self.lb_selected.setText("未选择版本")

    # ------------------------------------------------------------ 操作
    def _run_op(self, fn, ok_msg):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            return
        self.op_log.clear()
        self._set_buttons_enabled(False)
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, i=inst: fn(i, mirrors, report),
            on_progress=self._op,
            on_done=lambda msg: self._op_done(msg, ok_msg),
            on_error=self._op_error,
        )

    def _set_buttons_enabled(self, on):
        for b in (self.btn_refresh, self.btn_update_sel,
                  self.btn_req):
            b.setEnabled(on)

    def _op_done(self, msg, ok_msg):
        self._set_buttons_enabled(True)
        self._op(f"════════ ✅ {msg} ════════")
        QMessageBox.information(self, "完成", msg or ok_msg)
        self._info = None
        self._load_version_text()
        # 更新/回滚完成：强制刷新版本列表，让 Tags 的「当前」标记跟进新版本
        updater._VERSION_CACHE.update(key=None, at=0.0, info=None)
        self.refresh_versions()

    def _op_error(self, err):
        self._set_buttons_enabled(True)
        self._op("════════ ⚠ 操作未完全成功 ════════")
        self._op(str(err))
        QMessageBox.warning(self, "操作未完全成功", str(err))
        self._load_version_text()

    def update_selected(self):
        if not self._selected:
            QMessageBox.information(self, "提示", "请先刷新版本列表并选择一个版本")
            return
        inst = self.win.selected_instance()
        if not inst:
            return
        if self.win.pm.is_running():
            QMessageBox.warning(self, "提示", "请先停止正在运行的 ComfyUI 再更新")
            return
        target = self._selected
        self._run_op(
            lambda i, m, r: updater.update_to(i, target, m, r),
            f"已更新到 {target}")

    def install_requirements(self):
        self._run_op(
            lambda i, m, r: (updater.install_requirements(i, m, r), "依赖安装完毕")[1],
            "依赖安装完毕")
