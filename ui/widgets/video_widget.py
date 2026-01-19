import os
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import Qt
from typing import Optional

# Ensure the local directory is in the PATH so python-mpv can find the DLL
# We are in ui/widgets/video_widget.py
# Root is ../../
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB_DIR = os.path.join(ROOT_DIR, "libs")
if os.path.exists(LIB_DIR):
    os.environ["PATH"] = LIB_DIR + os.pathsep + os.environ["PATH"]

# Also add root directory as fallback
os.environ["PATH"] = ROOT_DIR + os.pathsep + os.environ["PATH"]

import mpv

def check_mpv_available() -> bool:
    """Checks if MPV library can be initialized."""
    try:
        m = mpv.MPV()
        m.terminate()
        return True
    except (OSError, Exception) as e:
        print(f"Error finding mpv: {e}")
        return False

class VideoWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        
        self.player: Optional[mpv.MPV] = None
        try:
            # vo='gpu' is generally best. keep_open='yes' prevents player closing on EOF
            self.player = mpv.MPV(wid=str(int(self.winId())), vo='gpu', keep_open='yes', log_handler=lambda level, prefix, text: None)
        except Exception as e:
            print(f"MPV Init failed: {e}")
            self.player = None

    def closeEvent(self, event):
        if self.player:
            self.player.terminate()
            self.player = None
        super().closeEvent(event)

    def load(self, filepath: str):
        if self.player:
            self.player.play(filepath)
            self.player.pause = True # Start paused

    def play(self):
        if self.player: self.player.pause = False

    def pause(self):
        if self.player: self.player.pause = True

    def toggle_pause(self) -> bool:
        if self.player: 
            self.player.pause = not self.player.pause
            return self.player.pause
        return True

    def seek(self, time_seconds: float):
        if self.player:
            self.player.time_pos = time_seconds

    def get_time(self) -> float:
        if self.player:
            return self.player.time_pos or 0.0
        return 0.0

    def get_duration(self) -> float:
        if self.player:
            return self.player.duration or 0.0
        return 0.0
    
    def set_volume(self, volume: int):
        if self.player:
            self.player.volume = volume

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._trigger_fullscreen()
            
    def _trigger_fullscreen(self):
        # We need to import these locally to avoid circular imports if those modules import this one
        # But efficiently we can just rely on the parent structure usually.
        # However, since we are moving things now, let's keep it abstract.
        p = self.window()
        
        # Check if parent has the method
        if hasattr(p, "toggle_video_fullscreen"):
             p.toggle_video_fullscreen(self)
        elif hasattr(p, "isFullScreen") and hasattr(p, "showNormal") and hasattr(p, "showFullScreen"):
            if p.isFullScreen(): p.showNormal()
            else: p.showFullScreen()
