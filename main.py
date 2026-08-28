# -*- coding: utf-8 -*-
"""ComfyUIBM启动器 —— 程序入口。

运行: python main.py
"""
import os
import sys


def main():
    try:
        from PyQt5 import QtCore  # noqa: F401
    except ImportError:
        print("缺少 PyQt5，请先安装依赖: pip install -r requirements.txt")
        input("按回车键退出…")
        sys.exit(1)

    # DPI 缩放必须在 QApplication 创建前设置（先读配置，异常时按默认处理）
    dpi = "auto"
    try:
        from launcher.config import Config
        dpi = str(Config().settings.get("dpi_scaling", "auto") or "auto").strip()
    except Exception:
        dpi = "auto"

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    if dpi == "off":
        QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    else:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        if dpi and dpi != "auto":
            os.environ["QT_SCALE_FACTOR"] = dpi   # 固定缩放因子

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
