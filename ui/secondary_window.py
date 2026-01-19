from PyQt6.QtWidgets import QWidget, QVBoxLayout

class SecondaryWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime Source")
        self.resize(500, 400)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
