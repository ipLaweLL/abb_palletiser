"""Launch the independent, full-size main GUI copy.

The engineering/test window remains available through main.py.
"""
import sys

from PySide6.QtWidgets import QApplication
from ui.user_main_window import UserMainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = UserMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
