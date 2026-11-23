import os
import sys


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StreamGrab.Downloader.1")
        except Exception:
            pass

    from .engine import activate_engine_updates, warm_up
    activate_engine_updates()

    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .icons import app_icon
    from .window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    fams = set(QFontDatabase.families())
    family = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "Inter") if f in fams), app.font().family())
    font = QFont(family)
    font.setPointSizeF(10)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    w = MainWindow()
    w.show()
    warm_up()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
