import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtCore import Qt

from sentry_app.logic import AppLogic
from sentry_app.ui.ui_qt_main import MainWindow

def main():
    app_logic = AppLogic()

    user_scale = app_logic.get_setting_float("UI_Scale")
    if user_scale <= 0: user_scale = 1.0

    app = QApplication(sys.argv)

    font = app.font()
    font.setPointSizeF(10.0 * user_scale)
    app.setFont(font)

    window = MainWindow(app_logic)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
