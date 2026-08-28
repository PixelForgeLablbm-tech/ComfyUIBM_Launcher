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
    system_dpi = 96
    try:
        from launcher.config import Config, dpi_scale_factor
        cfg = Config()
        dpi = str(cfg.settings.get("dpi_scaling", "auto") or "auto").strip()
        import ctypes
        try:
            d = int(ctypes.windll.user32.GetDpiForSystem())
            if d > 0:
                system_dpi = d
        except Exception:
            pass
    except Exception:
        dpi = "auto"

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    # 清理上次更新遗留的旧文件（"改名让位"更新时若旧进程仍锁着 .old 会残留）
    if getattr(sys, "frozen", False):
        try:
            old = sys.executable + ".old"
            if os.path.exists(old):
                os.remove(old)
        except Exception:
            pass

    if dpi == "off":
        QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    else:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        factor = dpi_scale_factor(dpi, system_dpi)
        if factor:
            # QT_SCALE_FACTOR 是乘数，反算后最终缩放 = 系统缩放 × factor = 用户所选值
            os.environ["QT_SCALE_FACTOR"] = factor

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
