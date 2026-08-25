# -*- coding: utf-8 -*-
"""模组（模型）管理页签：分类统计 / 搜索 / 排序 / 分页 / 导入 / 删除。"""
import os
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from launcher import model_manager
from ui.dialogs import confirm, open_in_explorer

PAGE_SIZE = 100


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


class CategoryItem(QWidget):
    """分类列表项：左侧文件夹名，右侧统计（数量 · 大小）右对齐。"""

    def __init__(self, name, label, path, parent=None):
        super().__init__(parent)
        self.name = name
        # 显式透明：WA_TranslucentBackground 对列表项 widget 不可靠，
        # 不透明会导致整行变成黑/深色底块
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        nm = QLabel(name)
        nm.setStyleSheet("background: transparent; font-weight: 600;")
        lay.addWidget(nm)
        lay.addStretch(1)
        # 统计部分：label 形如 "checkpoints · 2 · 3.00 KB"，去掉名称后右对齐
        parts = label.split(" · ")
        stats = " · ".join(parts[1:]) if len(parts) > 1 else ""
        st = QLabel(stats)
        st.setStyleSheet("background: transparent; color: #8b96a8; font-size: 12px;")
        lay.addWidget(st)


class ModelsTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._summary = []
        self._current_cat = None
        self._page = 1
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(12)

        # 工具栏卡片
        card = QGroupBox("工具")
        bar = QHBoxLayout(card)
        bar.setSpacing(8)
        self.lb_hint = QLabel("请先在「实例管理」中选择一个本地实例。")
        self.lb_hint.setProperty("dim", True)
        bar.addWidget(self.lb_hint, 1)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("搜索模型…")
        self.ed_search.setFixedWidth(170)
        self.ed_search.textChanged.connect(self._reset_page)
        bar.addWidget(self.ed_search)
        self.cb_sort = QComboBox()
        self.cb_sort.addItem("按大小", "size")
        self.cb_sort.addItem("按名称", "name")
        self.cb_sort.addItem("按时间", "time")
        self.cb_sort.setFixedWidth(100)
        self.cb_sort.currentIndexChanged.connect(self._reset_page)
        bar.addWidget(self.cb_sort)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(self.reload)
        bar.addWidget(self.btn_refresh)
        self.btn_open = QPushButton("打开目录")
        self.btn_open.setFixedHeight(32)
        self.btn_open.clicked.connect(self.open_dir)
        bar.addWidget(self.btn_open)
        self.btn_import = QPushButton("导入模型")
        self.btn_import.setObjectName("primary")
        self.btn_import.setFixedHeight(32)
        self.btn_import.clicked.connect(self.import_models)
        bar.addWidget(self.btn_import)
        lay.addWidget(card)

        # 主体：分类 + 文件
        body = QHBoxLayout()
        body.setSpacing(12)

        g_cat = QGroupBox("分类")
        cv = QVBoxLayout(g_cat)
        self.cat_list = QListWidget()
        self.cat_list.setObjectName("catList")
        self.cat_list.currentItemChanged.connect(self._on_category)
        cv.addWidget(self.cat_list)
        body.addWidget(g_cat)
        self.cat_list.setMinimumWidth(240)
        self._cat_entries = []   # [(item, widget, name)]

        g_file = QGroupBox("模型文件")
        fv = QVBoxLayout(g_file)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["文件名", "大小", "修改时间", "格式", "操作"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 表头模式：文件名 Stretch，其余 Fixed
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 166)   # 所在目录(94)+删除(60)+间距
        fv.addWidget(self.table, 1)
        pager = QHBoxLayout()
        self.lb_count = QLabel("")
        self.lb_count.setProperty("dim", True)
        pager.addWidget(self.lb_count)
        pager.addStretch(1)
        self.btn_prev = QPushButton("上一页")
        self.btn_prev.setObjectName("ghost")
        self.btn_prev.setFixedHeight(28)
        self.btn_prev.clicked.connect(lambda: self._goto(self._page - 1))
        self.lb_page = QLabel("")
        self.lb_page.setProperty("dim", True)
        self.btn_next = QPushButton("下一页")
        self.btn_next.setObjectName("ghost")
        self.btn_next.setFixedHeight(28)
        self.btn_next.clicked.connect(lambda: self._goto(self._page + 1))
        pager.addWidget(self.btn_prev)
        pager.addWidget(self.lb_page)
        pager.addWidget(self.btn_next)
        fv.addLayout(pager)
        body.addWidget(g_file, 1)
        lay.addLayout(body, 1)

    # ------------------------------------------------------------ 数据
    def on_instance_changed(self):
        self.reload()

    def reload(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            self.setEnabled(False)
            self._summary = []
            self.cat_list.clear()
            self.table.setRowCount(0)
            self.lb_hint.setText("请先在「实例管理」中选择一个本地实例。")
            return
        self.setEnabled(True)
        self.lb_hint.setText("正在扫描模型目录…（文件多可能需要几秒）")
        self.btn_refresh.setEnabled(False)
        self._scanning_for = inst.path
        self.win.tasks.start(
            lambda report, i=inst: model_manager.category_summary(i.path),
            on_done=lambda summary: self._on_scanned(summary),
            on_error=lambda e: (self.btn_refresh.setEnabled(True),
                                self.win.log(f"扫描失败: {e}")),
        )

    def _on_scanned(self, summary):
        self.btn_refresh.setEnabled(True)
        inst = self.win.selected_instance()
        if not inst or not inst.is_local or \
                inst.path != getattr(self, "_scanning_for", None):
            # 实例已变化/移除：丢弃过期扫描结果
            self.cat_list.clear()
            self.table.setRowCount(0)
            return
        if inst and inst.is_local:
            self.lb_hint.setText(
                f"模型目录: {model_manager.models_dir(inst.path)}")
        self._summary = summary
        keep = self._current_cat
        self.cat_list.blockSignals(True)
        self.cat_list.clear()
        self._cat_entries = []
        for c in summary:
            widget = CategoryItem(c["category"], c["label"], c["path"])
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            item.setToolTip(str(c["path"]))
            self.cat_list.addItem(item)
            self.cat_list.setItemWidget(item, widget)
            self._cat_entries.append((item, widget, c["category"]))
        self.cat_list.blockSignals(False)
        idx = 0
        for i, (_item, _w, name) in enumerate(self._cat_entries):
            if name == keep:
                idx = i
                break
        if self.cat_list.count():
            self.cat_list.setCurrentRow(idx)
        else:
            self.table.setRowCount(0)

    def _on_category(self, current, _prev):
        if current is None:
            self._current_cat = None
            self.table.setRowCount(0)
            return
        w = self.cat_list.itemWidget(current)
        self._current_cat = w.name if w else None
        self._reset_page()

    def _reset_page(self, *_):
        self._page = 1
        self._fill()

    def _goto(self, page):
        total = self._total_pages()
        if page < 1 or page > total:
            return
        self._page = page
        self._fill()

    def _filtered(self):
        cat = next((c for c in self._summary
                    if c["category"] == self._current_cat), None)
        if not cat:
            return []
        items = list(cat["items"])
        kw = self.ed_search.text().strip().lower()
        if kw:
            items = [i for i in items
                     if kw in i.name.lower() or kw in i.path.lower()]
        mode = self.cb_sort.currentData()
        if mode == "size":
            items.sort(key=lambda f: f.size, reverse=True)
        elif mode == "name":
            items.sort(key=lambda f: f.name.lower())
        else:
            items.sort(key=lambda f: f.mtime, reverse=True)
        return items

    def _total_pages(self):
        return max(1, -(-len(self._filtered()) // PAGE_SIZE))

    def _fill(self):
        items = self._filtered()
        total = len(items)
        total_pages = self._total_pages()
        start = (self._page - 1) * PAGE_SIZE
        page_items = items[start:start + PAGE_SIZE]

        self.table.setRowCount(len(page_items))
        for row, mf in enumerate(page_items):
            name_item = QTableWidgetItem(mf.name)
            name_item.setData(Qt.UserRole, mf.path)
            name_item.setToolTip(mf.path)
            size_item = QTableWidgetItem(model_manager.human_size(mf.size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            time_item = QTableWidgetItem(
                datetime.fromtimestamp(mf.mtime).strftime("%Y-%m-%d %H:%M"))
            ext_item = QTableWidgetItem(mf.ext.lstrip(".") or "无")
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, time_item)
            self.table.setItem(row, 3, ext_item)
            ops = _cell_widget([
                _cell_button("所在目录", "ghost",
                             lambda _=False, p=mf.path:
                             open_in_explorer(self, os.path.dirname(p))),
                _cell_button("删除", "danger",
                             lambda _=False, p=mf.path: self.delete_one(p)),
            ])
            self.table.setCellWidget(row, 4, ops)

        if not page_items and total:
            self.table.setRowCount(1)
            item = QTableWidgetItem("（当前筛选无结果）")
            item.setForeground(QColor("#9e9e9e"))
            self.table.setItem(0, 0, item)

        self.lb_count.setText(f"共 {total} 个文件")
        self.lb_page.setText(f"第 {self._page}/{total_pages} 页")
        self.btn_prev.setEnabled(self._page > 1)
        self.btn_next.setEnabled(self._page < total_pages)
        self._debug_geometry()

    def _debug_geometry(self):
        """运行时尺寸调试：设置环境变量 LAUNCHER_DEBUG_GEOM=1 时打印
        实际渲染的列宽与按钮宽度。"""
        import os
        if not os.environ.get("LAUNCHER_DEBUG_GEOM"):
            return
        header = self.table.horizontalHeader()
        for c in range(self.table.columnCount()):
            print(f"[DBG模型] col{c} 设置宽={self.table.columnWidth(c)} "
                  f"实际section={header.sectionSize(c)}")
        for row in range(min(self.table.rowCount(), 5)):
            w = self.table.cellWidget(row, 4)
            if w is None:
                continue
            btns = [b for b in w.findChildren(QPushButton)]
            info = ", ".join(
                f"'{b.text()}' w={b.width()} min={b.minimumWidth()} "
                f"max={b.maximumWidth()}" for b in btns)
            print(f"[DBG模型] r{row}c4 cell_w={w.width()} cell_h={w.height()} "
                  f"-> {info}")

    # ------------------------------------------------------------ 操作
    def import_models(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            return
        if not self._current_cat:
            QMessageBox.information(self, "提示", "请先选择一个分类")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择要导入的模型文件", "",
            f"模型文件 ({model_manager.MODEL_EXTS});;所有文件 (*)")
        if not files:
            return
        dst = model_manager.models_dir(inst.path) / self._current_cat
        self.btn_import.setEnabled(False)
        self.win.tasks.start(
            lambda report, paths=files, d=dst: model_manager.import_models(
                paths, str(d), progress=report),
            on_progress=lambda m: self.win.sb(m),
            on_done=lambda res: self._on_import_done(res),
            on_error=lambda e: self._on_import_error(e),
        )

    def _on_import_done(self, res):
        self.btn_import.setEnabled(True)
        ok, skipped, names = res
        self.win.log(f"导入完成：成功 {ok} 个，跳过 {skipped} 个")
        QMessageBox.information(
            self, "导入完成",
            f"成功 {ok} 个，跳过 {skipped} 个。\n"
            + (f"重命名：{', '.join(names[:5])}" if names else ""))
        self.reload()

    def _on_import_error(self, err):
        self.btn_import.setEnabled(True)
        QMessageBox.critical(self, "导入失败", str(err))

    def delete_one(self, path):
        if not confirm(self, "删除模型",
                       f"确定删除模型文件？\n（不可恢复）\n{path}"):
            return
        try:
            os.remove(path)
            self.win.log(f"已删除模型: {path}")
        except OSError as e:
            QMessageBox.critical(self, "删除失败", str(e))
        self.reload()

    def open_dir(self):
        inst = self.win.selected_instance()
        if not inst or not inst.is_local:
            return
        if self._current_cat:
            open_in_explorer(self, model_manager.models_dir(inst.path) / self._current_cat)
        else:
            open_in_explorer(self, model_manager.models_dir(inst.path))
