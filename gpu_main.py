"""Experimental GPU-based testing GUI. Standard main.py remains Matplotlib."""
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.gpu_pallet_view import GpuPallet3DView


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow(view_class=GpuPallet3DView)
    window.setWindowTitle("ABB Pallet Planner - GPU Viewer Prototype")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
