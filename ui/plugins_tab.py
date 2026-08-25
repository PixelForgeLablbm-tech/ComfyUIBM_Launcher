# -*- coding: utf-8 -*-
"""插件（自定义节点）管理页签：克隆安装 / 更新 / 依赖 / 禁用 / 删除。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from launcher import plugin_manager
from ui.dialogs import PluginInstallDialog, confirm, open_in_explorer


def _copy_line(text, tooltip=""):
    """只读文本框单元格：支持像浏览器一样拖动选字 + Ctrl+C / 右键复制。"""
    e = QLineEdit(text)
    e.setReadOnly(True)
    e.setFrame(False)
    e.setStyleSheet(
        "background: transparent; border: none; selection-background-color: #7c5cff;")
    e.setCursorPosition(0)
    if tooltip:
        e.setToolTip(tooltip)
    return e


def _cell_button(text, obj_name, callback, width=None):
    btn = QPushButton(text)
    btn.setObjectName(obj_name)

    # 尺寸策略：固定大小，不被布局拉伸挤压
    btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # 高度固定30，不要用setFixedSize把宽度锁死，改用setFixedHeight
    btn.setFixedHeight(30)

    if width is None:
        fm = btn.fontMetrics()
        # boundingRect 获取文字真实绘制边界，比horizontalAdvance更适合中文
        text_w = fm.boundingRect(text).width()
        # 预留足够空间：文字宽度 + qss左右padding(6*2) + 按钮原生边框余量
        calc_width = text_w + 24
        btn.setFixedWidth(calc_width)
    else:
        btn.setFixedWidth(width)

    # ⚠️注意：不要在setFixedSize之后再用padding，会挤压文字；
    # 把padding放到qss里面，不要用setStyleSheet内联padding，或者把padding算进宽度
    btn.setStyleSheet("""
        QPushButton{
            padding:3px 6px;
        }
    """)
    btn.clicked.connect(callback)
    return btn


def _cell_widget(buttons):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 2, 2, 2)   # 左右边距最小化
    lay.setSpacing(4)                    # 按钮间距最小化
    for b in buttons:
        lay.addWidget(b)
    if len(buttons) == 1:
        lay.addStretch(1)                # 单按钮：左对齐，不居中
    return w


class PluginsTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._plugins = []
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(12)

        # 卡片1：安装插件
        card = QGroupBox("安装插件")
        bar = QHBoxLayout(card)
        bar.setSpacing(8)
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText("粘贴插件 Git 地址，如 https://github.com/user/repo")
        self.ed_url.returnPressed.connect(self.clone_install)
        bar.addWidget(self.ed_url, 1)
        self.btn_clone = QPushButton("克隆安装")
        self.btn_clone.setObjectName("primary")
        self.btn_clone.setFixedHeight(32)
        self.btn_clone.clicked.connect(self.clone_install)
        bar.addWidget(self.btn_clone)
        self.btn_install_local = QPushButton("本地文件夹…")
        self.btn_install_local.setObjectName("ghost")
        self.btn_install_local.setFixedHeight(32)
        self.btn_install_local.clicked.connect(self.install_local)
        bar.addWidget(self.btn_install_local)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self.scan)
        bar.addWidget(self.btn_refresh)
        self.btn_gh = QPushButton("加速关")
        self.btn_gh.setObjectName("ghost")
        self.btn_gh.setFixedHeight(32)
        self.btn_gh.setToolTip("GitHub 加速（国内镜像）：克隆/更新插件走镜像前缀")
        self.btn_gh.clicked.connect(self.toggle_gh)
        bar.addWidget(self.btn_gh)
        lay.addWidget(card)

        # 卡片2：插件搜索（GitHub）
        card_s = QGroupBox("插件搜索（GitHub）")
        sv = QVBoxLayout(card_s)
        sv.setSpacing(6)
        srow = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("输入插件名称，如 Manager / Impact Pack / ControlNet")
        self.ed_search.returnPressed.connect(self.search_plugins)
        srow.addWidget(self.ed_search, 1)
        self.btn_search = QPushButton("搜索插件")
        self.btn_search.setObjectName("primary")
        self.btn_search.setFixedHeight(32)
        self.btn_search.clicked.connect(self.search_plugins)
        srow.addWidget(self.btn_search)
        sv.addLayout(srow)
        self.search_list = QListWidget()
        self.search_list.setMaximumHeight(120)
        self.search_list.itemDoubleClicked.connect(self._use_search_result)
        sv.addWidget(self.search_list)
        tip = QLabel("双击结果 → 自动填入上方克隆地址。需能访问 GitHub API（可开启代理/加速）。")
        tip.setProperty("dim", True)
        tip.setWordWrap(True)
        sv.addWidget(tip)
        lay.addWidget(card_s)

        # 提示行
        self.lb_hint = QLabel("请先在「实例管理」中选择一个本地实例。")
        self.lb_hint.setProperty("dim", True)
        lay.addWidget(self.lb_hint)

        # 表格
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["插件", "仓库 / 分支", "状态", "操作"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 表头模式：名称/仓库列 Stretch 自适应，状态/操作列 Fixed
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 132)   # 更新(60)+目录(60)+间距
        lay.addWidget(self.table, 1)

        # 底部操作
        foot = QHBoxLayout()
        self.btn_check = QPushButton("检查更新（全部）")
        self.btn_check.setFixedHeight(32)
        self.btn_check.clicked.connect(self.check_updates)
        foot.addWidget(self.btn_check)
        foot.addStretch(1)
        tip = QLabel("「更新」会自动暂存本地改动，更新成功后恢复")
        tip.setProperty("dim", True)
        foot.addWidget(tip)
        lay.addLayout(foot)

    # ------------------------------------------------------------ 数据
    def on_instance_changed(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            self.setEnabled(False)
            self.table.setRowCount(0)
            self.lb_hint.setText("请先在「实例管理」中选择一个本地实例。")
            return
        self.setEnabled(True)
        self.lb_hint.setText(
            f"custom_nodes 目录: {plugin_manager.custom_nodes_dir(inst.path)}")
        self._sync_gh_button()
        self.scan()

    def _sync_gh_button(self):
        on = bool(self.win.config.mirrors.get("gh_proxy"))
        self.btn_gh.setText("加速开" if on else "加速关")
        if on:
            self.btn_gh.setStyleSheet(
                "border-color: #7c5cff; color: #c4b5fd;")

    def toggle_gh(self):
        m = self.win.config.mirrors
        m["gh_proxy"] = not m.get("gh_proxy", False)
        self.win.config.save()
        self._sync_gh_button()
        self.win.sb("已开启 GitHub 加速" if m["gh_proxy"] else "已关闭加速（直连 GitHub）")

    def scan(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            return
        self.lb_hint.setText("正在读取插件信息…（git 查询，稍候）")
        self.btn_refresh.setEnabled(False)
        self._scanning_for = inst.path
        self.win.tasks.start(
            lambda report, i=inst: plugin_manager.scan_plugins(i.path),
            on_done=lambda plugins: self._fill(plugins),
            on_error=lambda e: (self.btn_refresh.setEnabled(True),
                                QMessageBox.critical(self, "扫描失败", str(e))),
        )

    def _fill(self, plugins):
        self.btn_refresh.setEnabled(True)
        inst = self.win.selected_instance()
        if not inst or not inst.is_local or \
                inst.path != getattr(self, "_scanning_for", None):
            # 实例已变化/移除：丢弃过期扫描结果
            self.table.setRowCount(0)
            return
        self._plugins = plugins
        inst = self.win.selected_instance()
        if inst and inst.is_local:
            self.lb_hint.setText(
                f"custom_nodes 目录: {plugin_manager.custom_nodes_dir(inst.path)}")
        self.table.setRowCount(len(plugins))
        for row, p in enumerate(plugins):
            # 第 1 列：插件名（可选中复制，路径存 property）
            name_line = _copy_line(p.name, tooltip=p.path)
            name_line.setProperty("plugin_path", p.path)
            self.table.setCellWidget(row, 0, name_line)

            # 第 2 列：仓库地址 / 分支（可选中复制）
            repo_text = p.remote or ("本地文件夹" if not p.is_git else "—")
            branch_tip = (f"分支: {p.branch}\n提交: {p.commit or '-'}"
                          if p.is_git else p.path)
            repo_line = _copy_line(repo_text, tooltip=branch_tip)
            self.table.setCellWidget(row, 1, repo_line)

            status_item = QTableWidgetItem(p.status_text)
            if p.error:
                status_item.setForeground(QColor("#f87171"))
            elif p.disabled:
                status_item.setForeground(QColor("#9aa5b8"))
            elif p.dirty:
                status_item.setForeground(QColor("#eab308"))
            else:
                status_item.setForeground(QColor("#34d399"))
            self.table.setItem(row, 2, status_item)
            buttons = []
            if p.is_git:
                buttons.append(_cell_button("更新", "ghost",
                                            lambda _=False, pl=p: self.update_one(pl)))
            buttons.append(_cell_button("目录", "ghost",
                                        lambda _=False, pl=p: open_in_explorer(self, pl.path)))
            self.table.setCellWidget(row, 3, _cell_widget(buttons))

        if not plugins:
            self.table.setRowCount(1)
            item = QTableWidgetItem("（custom_nodes 目录为空或未发现插件）")
            item.setForeground(QColor("#9e9e9e"))
            self.table.setItem(0, 0, item)
        self._debug_geometry()

    # ------------------------------------------------------------ 调试
    def _debug_geometry(self):
        """运行时尺寸调试：设置环境变量 LAUNCHER_DEBUG_GEOM=1 时打印
        实际渲染的列宽与按钮宽度（Qt 有隐形内边距/网格线像素，不能只看设置值）。"""
        import os
        if not os.environ.get("LAUNCHER_DEBUG_GEOM"):
            return
        header = self.table.horizontalHeader()
        for c in range(self.table.columnCount()):
            print(f"[DBG插件] col{c} 设置宽={self.table.columnWidth(c)} "
                  f"实际section={header.sectionSize(c)}")
        for row in range(min(self.table.rowCount(), 5)):
            for col in (2, 3):
                w = self.table.cellWidget(row, col)
                if w is None:
                    continue
                btns = [b for b in w.findChildren(QPushButton)]
                info = ", ".join(
                    f"'{b.text()}' w={b.width()} min={b.minimumWidth()} "
                    f"max={b.maximumWidth()}" for b in btns)
                print(f"[DBG插件] r{row}c{col} cell_w={w.width()} "
                      f"cell_h={w.height()} -> {info}")

    # ------------------------------------------------------------ 搜索
    def search_plugins(self):
        query = self.ed_search.text().strip()
        if not query:
            QMessageBox.information(self, "提示", "请输入插件名称")
            return
        self.search_list.clear()
        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜索中…")
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, q=query: self._search_impl(q, mirrors),
            on_done=self._on_search_done,
            on_error=self._on_search_error,
        )

    @staticmethod
    def _search_impl(query, mirrors):
        from launcher.github_search import search_repos
        return search_repos(query, mirrors)

    def _on_search_done(self, items):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("搜索插件")
        self.search_list.clear()
        if not items:
            self.search_list.addItem("（未找到匹配的插件）")
            self.win.sb("未找到匹配的插件")
            return
        self._search_results = items
        from launcher.github_search import is_official_author
        for repo in items:
            name = repo.get("name", "")
            owner = (repo.get("owner") or {}).get("login", "")
            stars = repo.get("stargazers_count", 0)
            desc = (repo.get("description") or "（无描述）")
            pushed = (repo.get("pushed_at") or "")[:10]
            official = is_official_author(owner)

            w = QWidget()
            w.setAttribute(Qt.WA_TranslucentBackground)
            w.setStyleSheet("background: transparent;")
            outer = QVBoxLayout(w)
            outer.setContentsMargins(12, 6, 12, 6)
            outer.setSpacing(2)

            # 第一行：作者/仓库名 + 官方徽标 + star + 更新日期
            row1 = QHBoxLayout()
            row1.setSpacing(8)
            nm = QLabel(f"{owner}/{name}" if owner else name)
            nm.setStyleSheet("background: transparent; font-weight: 700; font-size: 13px;")
            nm.setToolTip(repo.get("html_url", ""))
            row1.addWidget(nm)
            if official:
                badge = QLabel("官方/知名")
                badge.setStyleSheet(
                    "background: transparent; padding: 1px 7px; border-radius: 8px; "
                    "background-color: rgba(52,211,153,0.16); color: #34d399; "
                    "font-size: 11px;")
                row1.addWidget(badge)
            st = QLabel(f"⭐ {stars}")
            st.setStyleSheet("background: transparent; color: #eab308; font-size: 12px;")
            row1.addWidget(st)
            dt = QLabel(f"更新 {pushed}")
            dt.setStyleSheet("background: transparent; color: #8b96a8; font-size: 11.5px;")
            row1.addWidget(dt)
            row1.addStretch(1)
            outer.addLayout(row1)

            # 第二行：描述（单行省略）
            ds = QLabel(desc if len(desc) <= 70 else desc[:70] + "…")
            ds.setStyleSheet("background: transparent; color: #a3adc2; font-size: 12px;")
            ds.setFixedHeight(18)
            outer.addWidget(ds)

            item = QListWidgetItem()
            item.setSizeHint(w.sizeHint())
            item.setToolTip(f"{repo.get('html_url', '')}\n{desc}\n更新: {pushed}")
            item.setData(Qt.UserRole, repo.get("clone_url") or "")
            self.search_list.addItem(item)
            self.search_list.setItemWidget(item, w)
        self.win.sb(f"找到 {len(items)} 个插件")

    def _on_search_error(self, err):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("搜索插件")
        self.search_list.addItem("（搜索失败）")
        QMessageBox.warning(
            self, "搜索失败",
            f"{err}\n\n提示：确认能访问 GitHub API；可在「设置」启用代理，"
            "或开启 GitHub 加速后重试。")

    def _use_search_result(self, item):
        url = item.data(Qt.UserRole)
        if not url:
            return
        self.ed_url.setText(url)
        self.win.sb(f"已填入克隆地址：{url}")

    # ------------------------------------------------------------ 操作
    def clone_install(self):
        url = self.ed_url.text().strip()
        if not url:
            QMessageBox.information(self, "提示", "请粘贴插件 Git 仓库地址")
            return
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.warning(self, "提示", "请先选择一个本地实例")
            return
        self.btn_clone.setEnabled(False)
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, i=inst, u=url: plugin_manager.clone_plugin(
                i.path, u, mirrors=mirrors, progress=report),
            on_done=lambda info: self._after_install(info),
            on_error=lambda e: (self.btn_clone.setEnabled(True),
                                QMessageBox.critical(self, "克隆失败", str(e))),
        )

    def install_local(self):
        import os
        from PyQt5.QtWidgets import QFileDialog
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            QMessageBox.warning(self, "提示", "请先选择一个本地实例")
            return
        d = QFileDialog.getExistingDirectory(self, "选择插件文件夹")
        if not d:
            return
        name = os.path.basename(d.rstrip("\\/"))
        self.win.tasks.start(
            lambda report, i=inst, src=d, nm=name: plugin_manager.copy_plugin_folder(
                i.path, src, nm, progress=report),
            on_done=lambda info: self._after_install(info),
            on_error=lambda e: QMessageBox.critical(self, "复制失败", str(e)),
        )

    def _after_install(self, info):
        self.btn_clone.setEnabled(True)
        self.ed_url.clear()
        self.win.log(f"插件安装完成: {info.name}")
        QMessageBox.information(self, "安装完成",
                                f"插件「{info.name}」安装成功。\n重启 ComfyUI 后生效。")
        self.scan()

    def check_updates(self):
        if not self._plugins:
            return
        self.btn_check.setEnabled(False)
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, ps=self._plugins: plugin_manager.check_plugin_updates(
                ps, progress=report),
            on_progress=lambda m: self.win.sb(m),
            on_done=self._on_check_done,
            on_error=lambda e: (self.btn_check.setEnabled(True),
                                QMessageBox.critical(self, "检查失败", str(e))),
        )

    def _on_check_done(self, plugins):
        self.btn_check.setEnabled(True)
        self._fill(plugins)
        updatable = [p for p in plugins if p.has_update]
        self.win.log(f"插件更新检查完成，{len(updatable)} 个插件可更新")

    def update_one(self, p):
        if not p.is_git:
            QMessageBox.warning(self, "提示", f"「{p.name}」不是 Git 安装，无法更新。")
            return
        if not confirm(self, "更新插件",
                       f"确定更新插件「{p.name}」？\n（本地改动会自动暂存并在更新后恢复，"
                       f"更新后自动安装依赖）"):
            return
        inst = self.win.selected_instance()
        python = inst.resolve_python(
            self.win.config.settings.get("python_path", "python"))
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, pl=p: plugin_manager.update_plugin(
                pl, mirrors=mirrors, progress=report, python_exe=python),
            on_progress=lambda m: self.win.sb(m),
            on_done=lambda _r: (self.win.log(f"插件更新完成: {p.name}"),
                                self.scan()),
            on_error=lambda e: QMessageBox.critical(self, "更新失败",
                                                    f"{p.name}\n{e}"),
        )

    def install_deps(self, p):
        inst = self.win.selected_instance()
        python = inst.resolve_python(self.win.config.settings.get("python_path", "python"))
        mirrors = dict(self.win.config.mirrors)
        self.win.tasks.start(
            lambda report, pl=p: plugin_manager.install_requirements(
                pl.path, python, mirrors=mirrors, progress=report),
            on_progress=lambda m: self.win.sb(m),
            on_done=lambda msg: (self.win.log(f"依赖安装完成: {p.name}"),
                                 QMessageBox.information(self, "完成", str(msg))),
            on_error=lambda e: QMessageBox.critical(self, "安装失败", str(e)),
        )

    def toggle_one(self, p):
        plugin_manager.toggle_plugin(p)
        self.win.log(f"{'已禁用' if p.disabled else '已启用'}插件: {p.name}")
        self.win.sb(f"{'已禁用' if p.disabled else '已启用'}（重启后生效）")
        self.scan()

    def delete_one(self, p):
        if not confirm(self, "删除插件",
                       f"确定删除插件目录「{p.name}」？\n{p.path}\n（不可恢复）"):
            return
        plugin_manager.remove_plugin(p)
        self.win.log(f"已删除插件: {p.name}")
        self.scan()
