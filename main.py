# -*- coding: utf-8 -*-
"""ComfyUIBM启动器 —— 程序入口。

运行: python main.py
"""
import sys


def main():
    try:
        from PyQt5 import QtCore  # noqa: F401
    except ImportError:
        print("缺少 PyQt5，请先安装依赖: pip install -r requirements.txt")
        input("按回车键退出…")
        sys.exit(1)

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("ComfyUIBM启动器")
    app.setOrganizationName("ComfyUILauncher")

    from ui.theme import DARK_QSS
    app.setStyleSheet(DARK_QSS)

    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
