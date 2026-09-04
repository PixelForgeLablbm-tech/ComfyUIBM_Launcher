# -*- coding: utf-8 -*-
"""主题：深色 / 浅色 QSS，跟随系统（Windows 深色模式检测）。"""
import os

DARK_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
}
QMainWindow, QWidget {
    background: #304254;
    color: #d8dee9;
    font-size: 13px;
}
QListWidget#sideNav {
    background: #3a4e66;
    border: none;
    outline: 0;
    padding: 6px 2px;
}
QListWidget#sideNav::item {
    padding: 9px 10px;
    border-radius: 8px;
    margin: 2px 1px;
    color: #9aa5b8;
}
QListWidget#sideNav::item:hover {
    background: #42566e;
    color: #d8dee9;
}
QListWidget#sideNav::item:selected {
    background: rgba(124, 92, 255, 0.16);
    color: #c4b5fd;
    font-weight: 600;
}
QGroupBox {
    border: 1px solid #43576f;
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #8b96a8;
    font-size: 12px;
}
QLabel {
    color: #d8dee9;
}
QLabel[dim="true"] {
    color: #a3adc2;
}
QLabel[ok="true"] { color: #34d399; font-weight: 600; }
QLabel[bad="true"] { color: #f87171; font-weight: 600; }
QLabel[accent="true"] { color: #c4b5fd; font-weight: 600; }
QPushButton {
    background: #42566e;
    border: 1px solid #465a72;
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 20px;
    color: #d8dee9;
    font-size: 13px;
}
QPushButton:hover { background: #5a7290; border-color: #6b82a0; }
QPushButton:pressed { background: #33455b; }
QPushButton:disabled { color: #8fa2b8; background: #2f4154; border-color: #3a4c61; }
QPushButton#primary {
    background: rgba(124, 92, 255, 0.25);
    border-color: #7c5cff;
    color: #c4b5fd;
    font-weight: 600;
}
QPushButton#primary:hover { background: rgba(124, 92, 255, 0.52); border-color: #a48bff; }
QPushButton#danger {
    background: rgba(248, 113, 113, 0.16);
    border-color: #f87171;
    color: #fca5a5;
}
QPushButton#danger:hover { background: rgba(248, 113, 113, 0.42); }
QPushButton#ghost {
    background: transparent;
    border-color: #465a72;
}
QPushButton#ghost:hover { background: #5a7290; border-color: #6b82a0; }
/* 禁用态统一灰色（优先级高于 #primary/#danger 等 ID 规则） */
QPushButton#primary:disabled,
QPushButton#danger:disabled,
QPushButton#ghost:disabled {
    background: #2f4154;
    color: #8fa2b8;
    border-color: #3a4c61;
    font-weight: normal;
}
QLineEdit, QSpinBox, QComboBox {
    background: #3a4e66;
    border: 1px solid #465a72;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 22px;
    color: #d8dee9;
    font-size: 13px;
    selection-background-color: #7c5cff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #7c5cff;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #3a4e66;
    border: 1px solid #566b85;
    selection-background-color: rgba(124, 92, 255, 0.25);
    color: #d8dee9;
}
QCheckBox, QRadioButton { spacing: 7px; color: #d8dee9; font-size: 13px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px;
}
QTableWidget, QListWidget {
    background: #35475c;
    alternate-background-color: #3a4e66;
    border: 1px solid #43576f;
    border-radius: 8px;
    gridline-color: #3a4c61;
}
QHeaderView::section {
    background: #41566e;
    border: none;
    border-bottom: 1px solid #43576f;
    padding: 9px 10px;
    color: #8b96a8;
    font-weight: 600;
}
QTableWidget::item { padding: 7px 8px; }
QListWidget::item { padding: 7px 8px; }
QTableWidget::item:selected, QListWidget::item:selected {
    background: rgba(124, 92, 255, 0.25);
    color: #e5defc;
}
QListWidget#verList::item { padding: 0; border: none; }
QListWidget#verList::item:selected { background: rgba(124, 92, 255, 0.22); }
QListWidget#catList::item { padding: 0; border: none; }
QListWidget#catList::item:selected { background: rgba(124, 92, 255, 0.22); }
QPlainTextEdit {
    background: #2b3b4e;
    color: #a8c7a0;
    border: 1px solid #3a4c61;
    border-radius: 6px;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
}
QTabBar::tab {
    background: #3a4e66;
    color: #8b96a8;
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected { background: #42566e; color: #d8dee9; }
QStatusBar {
    background: #3a4e66;
    color: #8b96a8;
}
QStatusBar::item { border: none; }
QMenuBar { background: #3a4e66; color: #d8dee9; }
QMenuBar::item:selected { background: #42566e; }
QMenu {
    background: #3a4e66;
    color: #d8dee9;
    border: 1px solid #465a72;
}
QMenu::item:selected { background: rgba(124, 92, 255, 0.22); }
QDockWidget {
    color: #8b96a8;
    font-weight: 600;
}
QScrollBar:vertical {
    background: #35475c;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #465a72;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #566b85; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: #35475c; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #465a72; border-radius: 4px; }
QToolTip {
    background: #42566e;
    color: #d8dee9;
    border: 1px solid #566b85;
    padding: 4px 6px;
}
QProgressBar {
    background: #3a4e66;
    border: 1px solid #465a72;
    border-radius: 6px;
    text-align: center;
    color: #d8dee9;
}
QProgressBar::chunk { background: rgba(124, 92, 255, 0.6); border-radius: 5px; }
QSplitter::handle { background: #3a4c61; }
QSystemTrayIcon { background: transparent; }
"""

# 顶栏（浅色/深色各自定义）
DARK_QSS += """
QFrame#topBar { background: #3a4e66; border-bottom: 1px solid #3a4c61; }
QWidget#sidePanel { background: #3a4e66; }
QLabel#workflowPageTitle { font-size: 20px; font-weight: 700; color: #e5defc; }
QLabel#workflowResultState {
    color: #a3adc2; background: #35475c; border: 1px solid #465a72;
    border-radius: 11px; padding: 4px 10px; font-size: 12px;
}
QLabel#workflowResultState[state="busy"] { color: #c4b5fd; border-color: #7c5cff; }
QLabel#workflowResultState[state="success"] { color: #6ee7b7; border-color: #34d399; }
QLabel#workflowResultState[state="error"] { color: #fca5a5; border-color: #f87171; }
QFrame#workflowDropZone {
    background: #35475c; border: 1px dashed #566b85; border-radius: 10px;
}
QFrame#workflowDropZone[dragActive="true"] {
    background: rgba(124, 92, 255, 0.16); border: 2px solid #a48bff;
}
QLabel#workflowDropTitle { color: #e5defc; font-size: 15px; font-weight: 700; }
QLabel#workflowFileName { color: #d8dee9; padding: 4px 0; }
QLabel#workflowMissingBadge, QLabel#workflowInstalledBadge {
    border-radius: 10px; padding: 4px 9px; font-size: 12px; font-weight: 600;
}
QLabel#workflowMissingBadge { color: #fca5a5; background: rgba(248, 113, 113, 0.14); }
QLabel#workflowInstalledBadge { color: #6ee7b7; background: rgba(52, 211, 153, 0.14); }
QFrame#workflowMissingPane, QFrame#workflowInstalledPane {
    background: #35475c; border: 1px solid #43576f; border-radius: 8px;
}
QFrame#workflowMissingPane { border-color: #72545d; }
QLabel#workflowPaneTitle { color: #d8dee9; font-size: 14px; font-weight: 700; }
QLabel#workflowPaneTip { font-size: 11.5px; }
QListWidget#workflowMissingList, QListWidget#workflowInstalledList {
    background: #304254; border: none; border-radius: 6px; padding: 4px;
}
QFrame#workflowMissingItem, QFrame#workflowInstalledItem {
    background: #3a4e66; border: 1px solid #465a72; border-radius: 6px;
}
QFrame#workflowMissingItem { border-left: 3px solid #f87171; }
QFrame#workflowInstalledItem { border-left: 3px solid #34d399; }
QLabel#workflowPluginName { color: #e5defc; font-weight: 700; }
QLabel#workflowPluginNodes { color: #a3adc2; font-size: 11.5px; }
QFrame#workflowHint { background: #35475c; border: 1px solid #43576f; border-radius: 7px; }
QLabel#workflowHintTitle { color: #c4b5fd; font-weight: 700; }
QFrame#workflowDropZone QLabel,
QFrame#workflowMissingPane QLabel,
QFrame#workflowInstalledPane QLabel,
QFrame#workflowHint QLabel { background: transparent; }
QFrame#settingsGithub {
    background: #35475c; border: 1px solid #43576f; border-radius: 8px;
}
QLabel#settingsSectionTitle { background: transparent; color: #c4b5fd; font-weight: 700; }
QFrame#settingsGithub QLabel { background: transparent; }
"""

LIGHT_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
}
QMainWindow, QWidget {
    background: #f3f4f6;
    color: #2c313a;
    font-size: 13px;
}
QListWidget#sideNav {
    background: #eceef2;
    border: none;
    outline: 0;
    padding: 6px 2px;
}
QListWidget#sideNav::item {
    padding: 9px 10px;
    border-radius: 8px;
    margin: 2px 1px;
    color: #6b7280;
}
QListWidget#sideNav::item:hover {
    background: #dfe2e8;
    color: #2c313a;
}
QListWidget#sideNav::item:selected {
    background: rgba(124, 92, 255, 0.14);
    color: #6d4bd8;
    font-weight: 600;
}
QGroupBox {
    border: 1px solid #d5dae1;
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #6b7280;
    font-size: 12px;
}
QLabel {
    color: #2c313a;
}
QLabel[dim="true"] {
    color: #7a8290;
}
QLabel[ok="true"] { color: #0e9f6e; font-weight: 600; }
QLabel[bad="true"] { color: #dc2626; font-weight: 600; }
QLabel[accent="true"] { color: #6d4bd8; font-weight: 600; }
QPushButton {
    background: #ffffff;
    border: 1px solid #d5dae1;
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 20px;
    color: #2c313a;
    font-size: 13px;
}
QPushButton:hover { background: #e2e5ea; border-color: #b8c0cc; }
QPushButton:pressed { background: #d8dce3; }
QPushButton:disabled { color: #a6adba; background: #f3f4f6; border-color: #e2e5ea; }
QPushButton#primary {
    background: rgba(124, 92, 255, 0.12);
    border-color: #7c5cff;
    color: #6d4bd8;
    font-weight: 600;
}
QPushButton#primary:hover { background: rgba(124, 92, 255, 0.3); border-color: #9a7fff; }
QPushButton#danger {
    background: rgba(220, 38, 38, 0.08);
    border-color: #dc2626;
    color: #dc2626;
}
QPushButton#danger:hover { background: rgba(220, 38, 38, 0.22); }
QPushButton#ghost {
    background: transparent;
    border-color: #d5dae1;
}
QPushButton#ghost:hover { background: #e2e5ea; border-color: #b8c0cc; }
/* 禁用态统一灰色（优先级高于 #primary/#danger 等 ID 规则） */
QPushButton#primary:disabled,
QPushButton#danger:disabled,
QPushButton#ghost:disabled {
    background: #f3f4f6;
    color: #a6adba;
    border-color: #e2e5ea;
    font-weight: normal;
}
QLineEdit, QSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #d5dae1;
    border-radius: 7px;
    padding: 7px 10px;
    min-height: 22px;
    color: #2c313a;
    font-size: 13px;
    selection-background-color: #7c5cff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #7c5cff;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d5dae1;
    selection-background-color: rgba(124, 92, 255, 0.15);
    color: #2c313a;
}
QCheckBox, QRadioButton { spacing: 7px; color: #2c313a; font-size: 13px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px;
}
QTableWidget, QListWidget {
    background: #ffffff;
    alternate-background-color: #f7f8fa;
    border: 1px solid #e2e5ea;
    border-radius: 8px;
    gridline-color: #eceef2;
}
QHeaderView::section {
    background: #f3f4f6;
    border: none;
    border-bottom: 1px solid #e2e5ea;
    padding: 9px 10px;
    color: #6b7280;
    font-weight: 600;
}
QTableWidget::item { padding: 7px 8px; }
QListWidget::item { padding: 7px 8px; }
QTableWidget::item:selected, QListWidget::item:selected {
    background: rgba(124, 92, 255, 0.15);
    color: #3d2f8f;
}
QListWidget#verList::item { padding: 0; border: none; }
QListWidget#verList::item:selected { background: rgba(124, 92, 255, 0.15); }
QListWidget#catList::item { padding: 0; border: none; }
QListWidget#catList::item:selected { background: rgba(124, 92, 255, 0.15); }
QPlainTextEdit {
    background: #ffffff;
    color: #1f2937;
    border: 1px solid #e2e5ea;
    border-radius: 6px;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
}
QTabBar::tab {
    background: #eceef2;
    color: #6b7280;
    padding: 8px 18px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected { background: #ffffff; color: #2c313a; }
QStatusBar {
    background: #eceef2;
    color: #6b7280;
}
QStatusBar::item { border: none; }
QMenuBar { background: #eceef2; color: #2c313a; }
QMenuBar::item:selected { background: #dfe2e8; }
QMenu {
    background: #ffffff;
    color: #2c313a;
    border: 1px solid #d5dae1;
}
QMenu::item:selected { background: rgba(124, 92, 255, 0.12); }
QDockWidget {
    color: #6b7280;
    font-weight: 600;
}
QScrollBar:vertical {
    background: #f3f4f6;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c9cfd8;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #aab2bf; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: #f3f4f6; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #c9cfd8; border-radius: 4px; }
QToolTip {
    background: #ffffff;
    color: #2c313a;
    border: 1px solid #c3c9d2;
    padding: 4px 6px;
}
QProgressBar {
    background: #eceef2;
    border: 1px solid #d5dae1;
    border-radius: 6px;
    text-align: center;
    color: #2c313a;
}
QProgressBar::chunk { background: rgba(124, 92, 255, 0.5); border-radius: 5px; }
QSplitter::handle { background: #e2e5ea; }
QSystemTrayIcon { background: transparent; }
QFrame#topBar { background: #eceef2; border-bottom: 1px solid #e2e5ea; }
QWidget#sidePanel { background: #eceef2; }
QLabel#workflowPageTitle { font-size: 20px; font-weight: 700; color: #2c313a; }
QLabel#workflowResultState {
    color: #6b7280; background: #ffffff; border: 1px solid #d5dae1;
    border-radius: 11px; padding: 4px 10px; font-size: 12px;
}
QLabel#workflowResultState[state="busy"] { color: #6d4bd8; border-color: #7c5cff; }
QLabel#workflowResultState[state="success"] { color: #0e9f6e; border-color: #0e9f6e; }
QLabel#workflowResultState[state="error"] { color: #dc2626; border-color: #dc2626; }
QFrame#workflowDropZone {
    background: #ffffff; border: 1px dashed #aab2bf; border-radius: 10px;
}
QFrame#workflowDropZone[dragActive="true"] {
    background: rgba(124, 92, 255, 0.10); border: 2px solid #7c5cff;
}
QLabel#workflowDropTitle { color: #2c313a; font-size: 15px; font-weight: 700; }
QLabel#workflowFileName { color: #2c313a; padding: 4px 0; }
QLabel#workflowMissingBadge, QLabel#workflowInstalledBadge {
    border-radius: 10px; padding: 4px 9px; font-size: 12px; font-weight: 600;
}
QLabel#workflowMissingBadge { color: #dc2626; background: rgba(220, 38, 38, 0.09); }
QLabel#workflowInstalledBadge { color: #0e9f6e; background: rgba(14, 159, 110, 0.10); }
QFrame#workflowMissingPane, QFrame#workflowInstalledPane {
    background: #ffffff; border: 1px solid #d5dae1; border-radius: 8px;
}
QFrame#workflowMissingPane { border-color: #e4b4b4; }
QLabel#workflowPaneTitle { color: #2c313a; font-size: 14px; font-weight: 700; }
QLabel#workflowPaneTip { font-size: 11.5px; }
QListWidget#workflowMissingList, QListWidget#workflowInstalledList {
    background: #f7f8fa; border: none; border-radius: 6px; padding: 4px;
}
QFrame#workflowMissingItem, QFrame#workflowInstalledItem {
    background: #ffffff; border: 1px solid #dfe2e8; border-radius: 6px;
}
QFrame#workflowMissingItem { border-left: 3px solid #dc2626; }
QFrame#workflowInstalledItem { border-left: 3px solid #0e9f6e; }
QLabel#workflowPluginName { color: #2c313a; font-weight: 700; }
QLabel#workflowPluginNodes { color: #7a8290; font-size: 11.5px; }
QFrame#workflowHint { background: #ffffff; border: 1px solid #d5dae1; border-radius: 7px; }
QLabel#workflowHintTitle { color: #6d4bd8; font-weight: 700; }
QFrame#workflowDropZone QLabel,
QFrame#workflowMissingPane QLabel,
QFrame#workflowInstalledPane QLabel,
QFrame#workflowHint QLabel { background: transparent; }
QFrame#settingsGithub {
    background: #f7f8fa; border: 1px solid #d5dae1; border-radius: 8px;
}
QLabel#settingsSectionTitle { background: transparent; color: #6d4bd8; font-weight: 700; }
QFrame#settingsGithub QLabel { background: transparent; }
"""


def system_is_dark() -> bool:
    """Windows 深浅色模式检测（AppsUseLightTheme 注册表）；非 Windows 默认浅色。"""
    if os.name != "nt":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return val == 0
    except Exception:
        return False


def apply_theme(app, theme_name: str):
    """应用主题：dark / light / system。"""
    dark = theme_name != "light" and (theme_name != "system" or system_is_dark())
    app.setStyleSheet(DARK_QSS if dark else LIGHT_QSS)
    return dark

