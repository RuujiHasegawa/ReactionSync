import sys
import os
from PyQt6.QtWidgets import QApplication, QMessageBox

# Import ui components (after path check logic inside them usually, but we do it here too just in case)
from ui.widgets.video_widget import check_mpv_available
from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    if not check_mpv_available():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Missing MPV Library")
        msg.setText("Could not load 'libmpv'.")
        msg.setInformativeText(
            "Please download libmpv (mpv-2.dll) and place it in the 'libs/' folder.\n"
            f"Expected: {os.path.join(os.getcwd(), 'libs', 'mpv-2.dll')}\n"
        )
        msg.exec()
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
