import sys
import os
import atexit
from typing import Optional, Union, Tuple

# Ensure the local directory is in the PATH so python-mpv can find the DLL
# We look for "libs" folder first
LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs")
if os.path.exists(LIB_DIR):
    os.environ["PATH"] = LIB_DIR + os.pathsep + os.environ["PATH"]

# Also add current directory as fallback (legacy)
os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ["PATH"]

import mpv
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QFileDialog, QLabel, 
                             QSpinBox, QDoubleSpinBox, QFrame, QSizePolicy, QMessageBox, QStackedLayout)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QEvent
from PyQt6.QtGui import QMouseEvent, QCursor

# Constants
REFRESH_RATE_MS = 250
SYNC_THRESHOLD_SEC = 0.5
MIN_WINDOW_SIZE = (1000, 600)
OVERLAY_DEFAULT_SIZE = (320, 180)
OVERLAY_DEFAULT_POS = (20, 20)

# -----------------------------------------------------------------------------
# 1. MPV Check
# -----------------------------------------------------------------------------
def check_mpv_available() -> bool:
    """Checks if MPV library can be initialized."""
    try:
        m = mpv.MPV()
        m.terminate()
        return True
    except (OSError, Exception) as e:
        print(f"Error finding mpv: {e}")
        return False

# -----------------------------------------------------------------------------
# 2. Resizable/Draggable Container
# -----------------------------------------------------------------------------
class DragResizableWidget(QFrame):
    """
    A container that can be moved and resized.
    Uses a QStackedLayout:
      - Layer 0: Content (Video)
      - Layer 1: Grip Overlay (Transparent, handles mouse)
    to avoid event stealing by the child video widget.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setMinimumSize(100, 100)
        
        self.layout_ = QStackedLayout(self)
        self.layout_.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.layout_.setContentsMargins(0,0,0,0)

        # Grip Overlay
        self.grip = GripWidget(self)
        self.layout_.addWidget(self.grip) # Added LAST so it's ON TOP
        
        # Placeholder container for content
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0,0,0,0)
        self.layout_.insertWidget(0, self.content_container) # At bottom

    def set_content(self, widget: QWidget) -> None:
        """Replace the current content widget with a new one."""
        # Clear existing content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        self.content_layout.addWidget(widget)
        # Ensure grip is raised to capture mouse events on edges
        self.grip.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.grip.resize(self.size())


class GripWidget(QWidget):
    """Transparent overlay that handles drag/resize logic for its parent."""
    def __init__(self, parent_resizable: QWidget):
        super().__init__(parent_resizable)
        self.target = parent_resizable
        self.setMouseTracking(True)
        self.margin = 10
        self._is_moving = False
        self._is_resizing = False
        self._resize_edge: Optional[str] = None
        self._drag_start_pos = QPoint()
        
        # Transparent
        self.setStyleSheet("background-color: transparent;")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_edge(event.pos())
            if edge:
                self._is_resizing = True
                self._resize_edge = edge
                self._drag_start_pos = event.globalPosition().toPoint()
            else:
                self._is_moving = True
                self._drag_start_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_moving:
            # Calculate global value difference
            current_pos = event.globalPosition().toPoint()
            diff = current_pos - self._drag_start_pos
            self._drag_start_pos = current_pos
            
            # Apply to target's current position
            new_pos = self.target.pos() + diff
            
            # Boundary check if parent exists
            if self.target.parentWidget():
                p_rect = self.target.parentWidget().rect()
                # Keep somewhat inside boundaries
                new_x = max(0, min(new_pos.x(), p_rect.width() - 20))
                new_y = max(0, min(new_pos.y(), p_rect.height() - 20))
                self.target.move(new_x, new_y)
            else:
                self.target.move(new_pos)
            return

        if self._is_resizing and self._resize_edge:
            self._handle_resize(event.globalPosition().toPoint())
            return

        edge = self._get_edge(event.pos())
        self._update_cursor(edge)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._is_moving = False
        self._is_resizing = False
        self._resize_edge = None
        self.unsetCursor()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Trigger fullscreen on the content widget if applicable
            layout = self.target.content_layout # type: ignore
            if layout.count() > 0:
                 widget = layout.itemAt(0).widget()
                 if isinstance(widget, VideoWidget):
                     widget._trigger_fullscreen()

    def _get_edge(self, pos: QPoint) -> Optional[str]:
        r = self.rect()
        x, y, w, h = pos.x(), pos.y(), r.width(), r.height()
        m = self.margin
        
        on_left = x < m
        on_right = x > w - m
        on_top = y < m
        on_bottom = y > h - m
        
        if on_top and on_left: return 'top_left'
        if on_top and on_right: return 'top_right'
        if on_bottom and on_left: return 'bottom_left'
        if on_bottom and on_right: return 'bottom_right'
        if on_top: return 'top'
        if on_bottom: return 'bottom'
        if on_left: return 'left'
        if on_right: return 'right'
        return None

    def _update_cursor(self, edge: Optional[str]):
        if edge in ['top_left', 'bottom_right']:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ['top_right', 'bottom_left']:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edge in ['top', 'bottom']:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge in ['left', 'right']:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _handle_resize(self, global_mouse_pos: QPoint):
        diff = global_mouse_pos - self._drag_start_pos
        self._drag_start_pos = global_mouse_pos
        
        geo = self.target.geometry()
        new_geo = QRect(geo)
        
        dx, dy = diff.x(), diff.y()
        
        if self._resize_edge and 'top' in self._resize_edge:
            new_geo.setTop(geo.top() + dy)
        if self._resize_edge and 'bottom' in self._resize_edge:
            new_geo.setBottom(geo.bottom() + dy)
        if self._resize_edge and 'left' in self._resize_edge:
            new_geo.setLeft(geo.left() + dx)
        if self._resize_edge and 'right' in self._resize_edge:
            new_geo.setRight(geo.right() + dx)
             
        # Enforce Minimum Size 
        if new_geo.width() < self.target.minimumWidth():
            if self._resize_edge and 'left' in self._resize_edge: new_geo.setLeft(geo.left())
            else: new_geo.setRight(geo.right())
        
        if new_geo.height() < self.target.minimumHeight():
            if self._resize_edge and 'top' in self._resize_edge: new_geo.setTop(geo.top())
            else: new_geo.setBottom(geo.bottom())

        self.target.setGeometry(new_geo)


# -----------------------------------------------------------------------------
# 3. Video Widget (MPV wrapper)
# -----------------------------------------------------------------------------
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

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._trigger_fullscreen()
            
    def _trigger_fullscreen(self):
        # Traverse up to find MainWindow or SecondaryWindow
        p = self.window()
        
        if isinstance(p, SecondaryWindow):
            if p.isFullScreen(): p.showNormal()
            else: p.showFullScreen()
            return

        if isinstance(p, MainWindow):
            p.toggle_video_fullscreen(self)
            return
            
        # Fallback
        if p.isFullScreen(): p.showNormal()
        else: p.showFullScreen()


# -----------------------------------------------------------------------------
# 4. Main Window
# -----------------------------------------------------------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReactionSync - MPV Dual Player")
        self.resize(*MIN_WINDOW_SIZE)

        # Application State
        self.is_playing = False
        self.overlay_mode = False
        self.is_fullscreen_video = False
        self.duration_video1 = 1.0 
        self.offset = 0.0
        self._user_seeking = False

        # --- Initialize UI Components ---
        self.main_layout = QVBoxLayout(self)
        
        # 1. Video Components
        self._setup_videos()

        # 2. Controls
        self._setup_controls()

        # 3. Overlay Wrapper
        self._setup_overlay()
        
        # 4. State Management for Views
        # Track which logic source is where. 
        # Source 1 = Reaction (Master), Source 2 = Anime (Follower)
        # We start with S1 in Main, S2 in Secondary Window
        self.primary_video_widget = self.vid1_widget # The one in the main container
        self.secondary_video_widget = self.vid2_widget # The one in the other window/overlay

        # Start Timer
        self._setup_timer()

    def _setup_videos(self):
        # Master Video Container (Slot 1)
        self.vid1_label = QLabel("Reaction Video (Master)")
        self.vid1_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vid1_widget = VideoWidget()
        
        self.main_video_container = QWidget()
        self.main_video_layout = QVBoxLayout(self.main_video_container)
        self.main_video_layout.setContentsMargins(0,0,0,0)
        self.main_video_layout.addWidget(self.vid1_label)
        self.vid1_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_video_layout.addWidget(self.vid1_widget, stretch=1)
        
        self.main_layout.addWidget(self.main_video_container, stretch=1)

        # Secondary Video (Slot 2)
        self.vid2_widget = VideoWidget()
        self.second_window = SecondaryWindow()
        self.second_window.layout().addWidget(self.vid2_widget)
        self.second_window.show()

    def _setup_controls(self):
        self.controls_container = QWidget()
        self.controls_layout = QVBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0,0,0,0)
        
        # Seek Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.valueChanged.connect(self._on_slider_move)
        
        # Bottom Row
        btn_layout = QHBoxLayout()
        
        self.btn_load1 = QPushButton("Load Reaction")
        self.btn_load1.clicked.connect(lambda: self._load_file(1))
        
        self.btn_load2 = QPushButton("Load Anime")
        self.btn_load2.clicked.connect(lambda: self._load_file(2))
        
        self.btn_swap = QPushButton("Swap View")
        self.btn_swap.clicked.connect(self._swap_sources)
        
        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self._toggle_play)
        
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(-3600, 3600)
        self.spin_offset.setSingleStep(0.5)
        self.spin_offset.setValue(0.0)
        self.spin_offset.setPrefix("Anime Offset: ")
        self.spin_offset.valueChanged.connect(self._update_offset)
        
        self.btn_overlay = QPushButton("Toggle Overlay")
        self.btn_overlay.setCheckable(True)
        self.btn_overlay.toggled.connect(self._toggle_overlay_mode)

        # Volume
        self.vol1 = self._create_vol_slider(self.vid1_widget)
        self.vol2 = self._create_vol_slider(self.vid2_widget)

        btn_layout.addWidget(self.btn_load1)
        btn_layout.addWidget(self.btn_load2)
        btn_layout.addWidget(self.btn_swap)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_play)
        btn_layout.addStretch()
        btn_layout.addWidget(self.spin_offset)
        btn_layout.addWidget(self.btn_overlay)
        btn_layout.addWidget(QLabel("Vol 1:"))
        btn_layout.addWidget(self.vol1)
        btn_layout.addWidget(QLabel("Vol 2:"))
        btn_layout.addWidget(self.vol2)
        
        self.controls_layout.addWidget(self.slider)
        self.controls_layout.addLayout(btn_layout)
        
        self.main_layout.addWidget(self.controls_container)

    def _create_vol_slider(self, target_widget: VideoWidget) -> QSlider:
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(0, 100)
        s.setValue(100)
        s.setFixedWidth(80)
        s.valueChanged.connect(target_widget.set_volume)
        return s

    def _setup_overlay(self):
        # The overlay wrapper will hold whatever video is in the "secondary" slot when enabled
        self.overlay_wrapper = DragResizableWidget(self.main_video_container) 
        self.overlay_wrapper.setVisible(False)


    def _setup_timer(self):
        self.timer = QTimer()
        self.timer.setInterval(REFRESH_RATE_MS)
        self.timer.timeout.connect(self._update_progress)
        self.timer.start()

    # --- Video & Control Logic --- 

    def toggle_video_fullscreen(self, video_widget: VideoWidget):
        """Toggle fullscreen mode for the main window, hiding controls."""
        if self.is_fullscreen_video:
            self.showNormal()
            self.controls_container.show()
            self.vid1_label.show() 
            self.is_fullscreen_video = False
        else:
            self.controls_container.hide()
            self.vid1_label.hide()
            self.showFullScreen()
            self.is_fullscreen_video = True

    def _load_file(self, vid_idx: int):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mp4 *.mkv *.avi *.mov)")
        if not path: return

        if vid_idx == 1:
            self.vid1_widget.load(path)
            QTimer.singleShot(500, self._refresh_duration)
        else:
            self.vid2_widget.load(path)

    def _refresh_duration(self):
        d = self.vid1_widget.get_duration()
        if d > 0:
            self.duration_video1 = d
            self.slider.setRange(0, int(d * 10))

    def _toggle_play(self):
        self.is_playing = not self.is_playing
        self.btn_play.setText("Pause" if self.is_playing else "Play")
        if self.is_playing:
            self.vid1_widget.play()
            self.vid2_widget.play()
        else:
            self.vid1_widget.pause()
            self.vid2_widget.pause()
            self._sync_anime_pos()

    def _update_offset(self, val: float):
        self.offset = val
        if not self.is_playing:
            self._sync_anime_pos()

    def _sync_anime_pos(self):
        t1 = self.vid1_widget.get_time()
        t2_target = t1 - self.offset
        self.vid2_widget.seek(t2_target)

    def _update_progress(self):
        if not self._user_seeking and self.is_playing:
            t = self.vid1_widget.get_time()
            self.slider.setValue(int(t * 10))
            
            t2 = self.vid2_widget.get_time()
            target_t2 = t - self.offset
            
            # Sync check
            if abs(t2 - target_t2) > SYNC_THRESHOLD_SEC:
                 self.vid2_widget.seek(target_t2)

    def _on_slider_pressed(self):
        self._user_seeking = True
        self.vid1_widget.pause()
        self.vid2_widget.pause()

    def _on_slider_released(self):
        self._user_seeking = False
        val = self.slider.value() / 10.0
        self.vid1_widget.seek(val)
        self.vid2_widget.seek(val - self.offset)
        if self.is_playing:
            self.vid1_widget.play()
            self.vid2_widget.play()

    def _on_slider_move(self, val_int: int):
        if self._user_seeking:
            val = val_int / 10.0
            self.vid1_widget.seek(val)
            self.vid2_widget.seek(val - self.offset)

    # --- View Logic (Swap & Overlay) ---

    def _swap_sources(self):
        """
        Swaps the widgets between the Main Container (Slot 1) and the Secondary Container (Slot 2).
        Slot 2 can be either the Second Window or the Overlay Wrapper.
        """
        # 1. Identify current occupants
        current_primary = self.primary_video_widget
        current_secondary = self.secondary_video_widget

        # 2. Determine target containers
        container_1 = self.main_video_layout # Always main video layout
        
        # Container 2 depends on mode
        if self.overlay_mode:
            container_2_adder = self.overlay_wrapper.set_content
        else:
            # For HBoxLayout/VBoxLayout we addWidget. 
            container_2_adder = lambda w: (self.second_window.layout().addWidget(w), w.show())

        # 3. Detach both widgets to prevent parent conflicts
        current_primary.setParent(None)
        current_secondary.setParent(None)

        # 4. Swap Logic
        # New Primary -> Was Secondary
        # New Secondary -> Was Primary
        
        # Add new Primary (the old secondary) to Slot 1
        container_1.addWidget(current_secondary)
        current_secondary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        current_secondary.show()
        
        # Add new Secondary (the old primary) to Slot 2
        container_2_adder(current_primary)
        if not self.overlay_mode:
             self.second_window.show()

        # 5. Update State Tracking
        self.primary_video_widget = current_secondary
        self.secondary_video_widget = current_primary

    def _toggle_overlay_mode(self, enabled: bool):
        self.overlay_mode = enabled
        
        # The widget currently considered "secondary" is the one moving
        target_widget = self.secondary_video_widget
        
        if enabled:
            # Mode: Window -> Overlay
            self.second_window.hide()
            
            # Move widget to overlay
            target_widget.setParent(None)
            self.overlay_wrapper.set_content(target_widget)
            target_widget.show()
            
            # Show overlay
            self.overlay_wrapper.resize(*OVERLAY_DEFAULT_SIZE)
            self.overlay_wrapper.move(*OVERLAY_DEFAULT_POS)
            self.overlay_wrapper.show()
            self.overlay_wrapper.raise_()
            
        else:
            # Mode: Overlay -> Window
            self.overlay_wrapper.hide()
            
            # Move widget back to window
            target_widget.setParent(None)
            self.second_window.layout().addWidget(target_widget)
            target_widget.show()
            
            self.second_window.show()

    def closeEvent(self, event):
        self.second_window.close()
        super().closeEvent(event)


class SecondaryWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime Source")
        self.resize(500, 400)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)


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
