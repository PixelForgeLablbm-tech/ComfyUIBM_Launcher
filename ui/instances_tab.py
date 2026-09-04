# -*- coding: utf-8 -*-
"""实例管理页签：已配置实例 / 手动添加 / 自动扫描本机 ComfyUI。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout,
    QWidget,
)

from launcher.instance_scanner import detect_instances
from ui.dialogs import InstanceDialog, confirm


class _ElidedTextDelegate(QStyledItemDelegate):
    """单行显示长路径，保留完整内容供鼠标悬停查看。"""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = opt.fontMetrics.elidedText(
            opt.text, Qt.ElideMiddle, max(0, opt.rect.width() - 16))
        super().paint(painter, opt, index)


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
    # 统一操作区的安全边距，避免单元格边缘裁切按钮的边框/圆角。
    lay.setContentsMargins(10, 5, 10, 5)
    lay.setSpacing(6)
    for b in buttons:
        lay.addWidget(b)
    if len(buttons) == 1:
        lay.addStretch(1)                # 单按钮：左对齐，不居中
    return w


class InstancesTab(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self._detected = []
        self._build()

    # ------------------------------------------------------------ UI
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(14)

        # 卡片1：已配置实例
        card1 = QGroupBox("已配置实例（启动时使用）")
        v1 = QVBoxLayout(card1)
        self.table_configured = QTableWidget(0, 4)
        self.table_configured.setHorizontalHeaderLabels(
            ["名称", "ComfyUI 路径", "Python", "操作"])
        self.table_configured.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_configured.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_configured.setWordWrap(False)
        path_delegate = _ElidedTextDelegate(self.table_configured)
        self.table_configured.setItemDelegateForColumn(1, path_delegate)
        self.table_configured.setItemDelegateForColumn(2, path_delegate)
        # 名称、Python、操作使用稳定宽度；剩余空间全部让给 ComfyUI 路径。
        # 这样长 Python 路径不会挤压或遮住右侧操作按钮。
        h1 = self.table_configured.horizontalHeader()
        h1.setSectionResizeMode(0, QHeaderView.Fixed)
        h1.setSectionResizeMode(1, QHeaderView.Stretch)
        h1.setSectionResizeMode(2, QHeaderView.Fixed)
        h1.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_configured.verticalHeader().setVisible(False)
        self.table_configured.verticalHeader().setDefaultSectionSize(44)
        self.table_configured.setColumnWidth(0, 165)
        self.table_configured.setColumnWidth(2, 220)
        self.table_configured.setColumnWidth(3, 272)   # 三个按钮 + 间距 + 两侧安全边距
        v1.addWidget(self.table_configured)
        lay.addWidget(card1, 2)

        # 卡片2：手动添加
        card2 = QGroupBox("手动添加实例")
        v2 = QHBoxLayout(card2)
        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText("选择或输入包含 main.py、comfy、models 的 ComfyUI 根目录")
        btn_browse = QPushButton("浏览…")
        btn_browse.setObjectName("ghost")
        btn_browse.setFixedHeight(32)
        btn_browse.clicked.connect(self._browse)
        self.btn_add = QPushButton("添加实例")
        self.btn_add.setObjectName("primary")
        self.btn_add.setFixedHeight(32)
        self.btn_add.clicked.connect(self._add_custom)
        v2.addWidget(self.ed_path, 1)
        v2.addWidget(btn_browse)
        v2.addWidget(self.btn_add)
        lay.addWidget(card2)

        # 卡片3：扫描本机
        card3 = QGroupBox("扫描本机 ComfyUI 安装")
        v3 = QVBoxLayout(card3)
        head = QHBoxLayout()
        tip = QLabel("自动查找盘符根目录 / 已配置实例目录 / 用户目录下的 ComfyUI（含子目录布局）")
        tip.setProperty("dim", True)
        head.addWidget(tip)
        head.addStretch(1)
        self.btn_scan = QPushButton("重新扫描")
        self.btn_scan.setFixedHeight(32)
        self.btn_scan.clicked.connect(self.scan)
        head.addWidget(self.btn_scan)
        v3.addLayout(head)
        self.table_detected = QTableWidget(0, 5)
        self.table_detected.setHorizontalHeaderLabels(
            ["名称", "路径", "版本", "Python", "操作"])
        self.table_detected.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_detected.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_detected.setWordWrap(False)
        self.table_detected.setItemDelegateForColumn(1, _ElidedTextDelegate(self.table_detected))
        # 表头模式：路径 Stretch，其余 Fixed
        h2 = self.table_detected.horizontalHeader()
        h2.setSectionResizeMode(0, QHeaderView.Fixed)
        h2.setSectionResizeMode(1, QHeaderView.Stretch)
        h2.setSectionResizeMode(2, QHeaderView.Fixed)
        h2.setSectionResizeMode(3, QHeaderView.Fixed)
        h2.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table_detected.verticalHeader().setVisible(False)
        self.table_detected.verticalHeader().setDefaultSectionSize(40)
        self.table_detected.setColumnWidth(0, 150)
        self.table_detected.setColumnWidth(2, 90)
        self.table_detected.setColumnWidth(3, 100)
        self.table_detected.setColumnWidth(4, 102)    # 单按钮 + 左对齐
        v3.addWidget(self.table_detected)
        lay.addWidget(card3, 3)

    # ------------------------------------------------------------ 数据
    def reload(self):
        """刷新已配置实例表。"""
        cfg = self.win.config
        insts = self.win.inst_mgr.all()
        self.table_configured.setRowCount(len(insts))
        for row, inst in enumerate(insts):
            name_item = QTableWidgetItem(inst.name)
            if inst.uid == cfg.current_instance_id:
                name_item.setText(f"{inst.name}  ★当前")
                name_item.setForeground(QColor("#c4b5fd"))
            path_item = QTableWidgetItem(inst.describe())
            py_item = QTableWidgetItem(inst.python or "(自动/全局)")
            path_item.setToolTip(inst.describe())
            py_item.setToolTip(inst.python or "(自动/全局)")
            ops = _cell_widget([
                _cell_button("设为当前", "ghost",
                             lambda _=False, uid=inst.uid: self.use_instance(uid),
                             width=84),
                _cell_button("编辑", "ghost",
                             lambda _=False, uid=inst.uid: self.edit_instance(uid),
                             width=58),
                _cell_button("移除", "danger",
                             lambda _=False, uid=inst.uid: self.remove_instance(uid),
                             width=58),
            ])
            self.table_configured.setItem(row, 0, name_item)
            self.table_configured.setItem(row, 1, path_item)
            self.table_configured.setItem(row, 2, py_item)
            self.table_configured.setCellWidget(row, 3, ops)
        self.table_configured.setRowCount(len(insts))
        self._debug_geometry("已配置")

    def scan(self):
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("扫描中…")

        def work(report):
            return detect_instances(self.win.config)

        self.win.tasks.start(
            work,
            on_done=self._on_scanned,
            on_error=lambda e: self._scan_error(e),
        )

    def _on_scanned(self, detected):
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("重新扫描")
        self._detected = detected
        cfg = self.win.config
        added_ids = {i.get("path", "").lower() for i in cfg.instances}
        self.table_detected.setRowCount(len(detected))
        for row, d in enumerate(detected):
            is_added = d["path"].lower() in added_ids
            name_item = QTableWidgetItem(d["name"])
            path_item = QTableWidgetItem(d["path"])
            path_item.setToolTip(d["path"])
            ver_item = QTableWidgetItem(d.get("version") or "未知")
            py_item = QTableWidgetItem("✓ 已找到" if d.get("python")
                                       else "✗ 未找到")
            if is_added:
                btn = _cell_button("设为当前", "ghost",
                                   lambda _=False, p=d["path"]: self._use_by_path(p))
            else:
                btn = _cell_button("添加", "primary",
                                   lambda _=False, p=d["path"]: self._add_by_path(p))
            self.table_detected.setItem(row, 0, name_item)
            self.table_detected.setItem(row, 1, path_item)
            self.table_detected.setItem(row, 2, ver_item)
            self.table_detected.setItem(row, 3, py_item)
            self.table_detected.setCellWidget(row, 4, _cell_widget([btn]))
        self.win.log(f"扫描完成，发现 {len(detected)} 个 ComfyUI 安装")
        self._debug_geometry("扫描结果")

    def _debug_geometry(self, tag):
        """运行时尺寸调试：设置环境变量 LAUNCHER_DEBUG_GEOM=1 时打印
        实际渲染的列宽与按钮宽度。"""
        import os
        if not os.environ.get("LAUNCHER_DEBUG_GEOM"):
            return
        for tbl in (self.table_configured, self.table_detected):
            header = tbl.horizontalHeader()
            for c in range(tbl.columnCount()):
                print(f"[DBG实例:{tag}] col{c} 设置宽={tbl.columnWidth(c)} "
                      f"实际section={header.sectionSize(c)}")
            for row in range(min(tbl.rowCount(), 5)):
                for col in range(tbl.columnCount()):
                    w = tbl.cellWidget(row, col)
                    if w is None:
                        continue
                    btns = [b for b in w.findChildren(QPushButton)]
                    info = ", ".join(
                        f"'{b.text()}' w={b.width()} min={b.minimumWidth()} "
                        f"max={b.maximumWidth()}" for b in btns)
                    print(f"[DBG实例:{tag}] r{row}c{col} cell_w={w.width()} "
                          f"cell_h={w.height()} -> {info}")

    def _scan_error(self, err):
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("重新扫描")
        QMessageBox.critical(self, "扫描失败", str(err))

    # ------------------------------------------------------------ 操作
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择 ComfyUI 目录")
        if d:
            self.ed_path.setText(d)

    def _add_custom(self):
        p = self.ed_path.text().strip()
        if not p:
            QMessageBox.information(self, "提示", "请选择 ComfyUI 目录")
            return
        self._add_by_path(p)

    def _add_by_path(self, path):
        try:
            inst = self.win.inst_mgr.add_probe(path)
        except Exception as e:
            QMessageBox.critical(self, "添加失败", str(e))
            return
        self.win.config.current_instance_id = inst.uid
        self.win.config.save()
        self.win.log(f"已添加实例: {inst.name} ({path})")
        self.win.sb(f"已添加实例：{inst.name}")
        self.win.instances_changed(select_uid=inst.uid)
        self.reload()

    def _use_by_path(self, path):
        for inst in self.win.inst_mgr.all():
            if inst.path == path:
                self.use_instance(inst.uid)
                return

    def use_instance(self, uid):
        self.win.config.current_instance_id = uid
        self.win.config.save()
        self.win.sb("已切换为当前实例")
        self.reload()
        self.win.instances_changed(select_uid=uid)

    def edit_instance(self, uid):
        inst = self.win.inst_mgr.get(uid)
        if not inst:
            return
        dlg = InstanceDialog(inst=inst, parent=self.win)
        if dlg.exec_() == dlg.Accepted:
            self.win.inst_mgr.update(inst)
            self.win.log(f"已保存实例: {inst.name}")
            self.reload()
            self.win.instances_changed(select_uid=uid)

    def remove_instance(self, uid):
        inst = self.win.inst_mgr.get(uid)
        if not inst:
            return
        if not confirm(self, "移除实例",
                       f"确定移除实例「{inst.name}」？\n（不会删除磁盘上的任何文件）"):
            return
        self.win.inst_mgr.remove(uid)
        if self.win.config.current_instance_id == uid:
            self.win.config.current_instance_id = None
            self.win.config.save()
        self.win.log(f"已移除实例: {inst.name}")
        self.reload()
        self.win.instances_changed()
