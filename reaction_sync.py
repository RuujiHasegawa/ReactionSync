import sys
import os

# Ensure the local directory is in the PATH so python-mpv can find the DLL
os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "libs" + os.pathsep + os.environ["PATH"]

import mpv
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QFileDialog, QLabel, 
                             QSpinBox, QDoubleSpinBox, QFrame, QSizePolicy, QMessageBox, QStackedLayout)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QEvent
from PyQt6.QtGui import QMouseEvent, QCursor

# -----------------------------------------------------------------------------
# 1. MPV Check
# -----------------------------------------------------------------------------
def check_mpv_available():
    """Checks if MPV library can be initialized."""
    try:
        # Just try to instantiate. If no libmpv found, it usually raises OSError or similar.
        # python-mpv usually handles searching the PATH, but on Windows 
        # the user often needs to put mpv-2.dll or mpv-1.dll next to the script.
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
    def __init__(self, parent=None):
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
        
        # We also need a placeholder container for the content if we want to add/remove
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0,0,0,0)
        self.layout_.insertWidget(0, self.content_container) # At bottom

    def set_content(self, widget):
        # Clear existing content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        self.content_layout.addWidget(widget)
        # Ensure grip is raised
        self.grip.raise_()

    # Pass resize events to grip to ensure it stays sized (though layout handles it)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.resize(self.size())


class GripWidget(QWidget):
    """Transparent overlay that handles drag/resize logic for its parent."""
    def __init__(self, parent_resizable):
        super().__init__(parent_resizable)
        self.target = parent_resizable
        self.setMouseTracking(True)
        self.margin = 10
        self._is_moving = False
        self._is_resizing = False
        self._resize_edge = None
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
                self._drag_start_pos = event.pos()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_moving:
            # Move the TARGET (parent)
            # mapToParent of the *target*?
            # event.pos() is relative to Grip. Grip is at (0,0) of Target.
            # So event.pos() IS relative to Target.
            # We want to move Target relative to Target's Parent.
            
            # Diff calculation:
            # We need to move the target such that the mouse stays at the same relative spot.
            # simple 'move' logic:
            # new_top_left_of_target = event.globalPosition() - offset
            # But simpler:
            
            target_parent_pos = self.target.mapToParent(event.pos() - self._drag_start_pos)
            
            # Boundary check
            if self.target.parentWidget():
                p_rect = self.target.parentWidget().rect()
                new_x = max(0, min(target_parent_pos.x(), p_rect.width() - 20))
                new_y = max(0, min(target_parent_pos.y(), p_rect.height() - 20))
                self.target.move(new_x, new_y)
            else:
                self.target.move(target_parent_pos)
            return

        if self._is_resizing:
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
        # Forward double clicks to the content? Or handle fullscreen?
        # Let's try to assume double click on overlay means fullscreen current overlay content.
        # But for now, let's just pass it through or ignore. 
        # Actually, user wants fullscreen. 
        # If we double click the overlay, it should fullscreen the overlay (Vid2).
        if event.button() == Qt.MouseButton.LeftButton:
            # Trigger fullscreen on the vid2 widget?
            # Or better: check if we have a content widget
            layout = self.target.content_layout
            if layout.count() > 0:
                 widget = layout.itemAt(0).widget()
                 if isinstance(widget, VideoWidget):
                     widget._trigger_fullscreen()

    def _get_edge(self, pos):
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

    def _update_cursor(self, edge):
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

    def _handle_resize(self, global_mouse_pos):
        diff = global_mouse_pos - self._drag_start_pos
        self._drag_start_pos = global_mouse_pos
        
        geo = self.target.geometry()
        new_geo = QRect(geo)
        
        dx, dy = diff.x(), diff.y()
        
        if 'top' in self._resize_edge:
            new_geo.setTop(geo.top() + dy)
        if 'bottom' in self._resize_edge:
            new_geo.setBottom(geo.bottom() + dy)
        if 'left' in self._resize_edge:
            new_geo.setLeft(geo.left() + dx)
        if 'right' in self._resize_edge:
            new_geo.setRight(geo.right() + dx)
             
        if new_geo.width() < self.target.minimumWidth():
            if 'left' in self._resize_edge: new_geo.setLeft(geo.left())
            else: new_geo.setRight(geo.right())
        
        if new_geo.height() < self.target.minimumHeight():
            if 'top' in self._resize_edge: new_geo.setTop(geo.top())
            else: new_geo.setBottom(geo.bottom())

        self.target.setGeometry(new_geo)

# -----------------------------------------------------------------------------
# 3. Video Widget (MPV wrapper)
# -----------------------------------------------------------------------------
class VideoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        
        # Initialize MPV
        # vo='wid' allows embedding. input_default_bindings=True gives basic key bindings if focused
        try:
            self.player = mpv.MPV(wid=str(int(self.winId())), vo='gpu', keep_open='yes', log_handler=lambda level, prefix, text: None)
        except Exception as e:
            # Fallback for debugging if dll missing, though check_mpv_available should catch it
            print(f"MPV Init failed: {e}")
            self.player = None

    def load(self, filepath):
        if self.player:
            self.player.play(filepath)
            self.player.pause = True # Start paused

    def play(self):
        if self.player: self.player.pause = False

    def pause(self):
        if self.player: self.player.pause = True

    def toggle_pause(self):
        if self.player: 
            self.player.pause = not self.player.pause
            return self.player.pause
        return True

    def seek(self, time_seconds):
        if self.player:
            self.player.time_pos = time_seconds

    def get_time(self):
        if self.player:
            return self.player.time_pos or 0
        return 0

    def get_duration(self):
        if self.player:
            return self.player.duration or 0
        return 0
    
    def set_volume(self, volume):
        if self.player:
            self.player.volume = volume

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._trigger_fullscreen()
            
    def _trigger_fullscreen(self):
        # We need to find the MainWindow to handle its specific fullscreen logic (Hiding controls)
        # Or if we are in a SecondaryWindow, just toggle that.
        
        # Traverse up to find MainWindow or SecondaryWindow
        p = self.window()
        
        # If it's the secondary window (just a wrapper), simple window fullscreen works
        if isinstance(p, SecondaryWindow):
            if p.isFullScreen(): p.showNormal()
            else: p.showFullScreen()
            return

        # If it's the MainWindow, we need to call a method on it to hide/show controls
        if isinstance(p, MainWindow):
            p.toggle_video_fullscreen(self) # Pass self so it knows WHICH video if needed
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
        self.resize(1000, 600)

        # State
        self.overlay_mode = False
        self.duration_video1 = 1.0 # Avoid div by zero
        self.is_playing = False
        self.offset = 0.0
        self.is_fullscreen_video = False # Track refined fullscreen state

        # UI Components
        self._init_ui()
        
        # Timer for UI updates (slider position)
        self.timer = QTimer()
        self.timer.setInterval(250) # 4 times a second
        self.timer.timeout.connect(self._update_progress)
        self.timer.start()

    def _init_ui(self):
        # --- Layouts ---
        self.main_layout = QVBoxLayout(self)
        
        # --- Video 1 (Reaction) - Inside Main Window ---
        self.vid1_label = QLabel("Reaction Video (Master)")
        self.vid1_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vid1 = VideoWidget()
        
        # We put Vid1 in a container so we can treat it similarly to before if needed
        self.vid1_container = QWidget()
        self.vid1_layout = QVBoxLayout(self.vid1_container)
        self.vid1_layout.setContentsMargins(0,0,0,0)
        self.vid1_layout.addWidget(self.vid1_label)
        
        # Ensure video widget expands
        self.vid1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.vid1_layout.addWidget(self.vid1, stretch=1)
        
        self.main_layout.addWidget(self.vid1_container, stretch=1)

        # --- Video 2 (Anime) - Separate Window ---
        self.vid2 = VideoWidget()
        self.second_window = SecondaryWindow()
        self.second_window.layout().addWidget(self.vid2)
        # We show it by default
        self.second_window.show()

        # --- Overlay Container (Global Wrapper used in Main Window) ---
        # Used when we toggle overlay mode
        self.overlay_wrapper = DragResizableWidget(self.vid1) 
        self.overlay_wrapper.setVisible(False)
        self.overlay_wrapper.setLayout(QVBoxLayout())
        self.overlay_wrapper.layout().setContentsMargins(0,0,0,0)

        # --- Controls Area ---
        # Wrap everything in a container for easy hiding
        self.controls_container = QWidget()
        self.controls_layout = QVBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0,0,0,0)
        
        # Seek Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.valueChanged.connect(self._on_slider_move)
        self._user_seeking = False
        
        # Buttons & Inputs
        btn_layout = QHBoxLayout()
        
        self.btn_load1 = QPushButton("Load Reaction")
        self.btn_load1.clicked.connect(lambda: self._load_file(1))
        
        self.btn_load2 = QPushButton("Load Anime")
        self.btn_load2.clicked.connect(lambda: self._load_file(2))
        
        self.btn_swap = QPushButton("Swap View")
        self.btn_swap.clicked.connect(self._swap_sources)
        
        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self._toggle_play)
        
        # Offset
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(-3600, 3600)
        self.spin_offset.setSingleStep(0.5)
        self.spin_offset.setValue(0.0)
        self.spin_offset.setPrefix("Anime Offset: ")
        self.spin_offset.valueChanged.connect(self._update_offset)
        
        # Overlay Toggle
        self.btn_overlay = QPushButton("Toggle Overlay")
        self.btn_overlay.setCheckable(True)
        self.btn_overlay.toggled.connect(self._toggle_overlay_mode)

        # Volume Controls
        self.vol1 = QSlider(Qt.Orientation.Horizontal)
        self.vol1.setRange(0, 100)
        self.vol1.setValue(100)
        self.vol1.setFixedWidth(80)
        self.vol1.setToolTip("Reaction Vol")
        self.vol1.valueChanged.connect(self.vid1.set_volume)
        
        self.vol2 = QSlider(Qt.Orientation.Horizontal)
        self.vol2.setRange(0, 100)
        self.vol2.setValue(100)
        self.vol2.setFixedWidth(80)
        self.vol2.setToolTip("Anime Vol")
        self.vol2.valueChanged.connect(self.vid2.set_volume)

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

    def toggle_video_fullscreen(self, video_widget):
        """
        Custom logic to hide controls/labels when making the video full in the main window.
        """
        if self.is_fullscreen_video:
            # Exit Fullscreen
            self.showNormal()
            self.controls_container.show()
            self.vid1_label.show() # Assuming we only fullscreen vid1 here usually, but if swapped...
            
            # If swapped, we might have vid2 in main. We should just show whatever label is there.
            # But wait, self.vid1_label text is static "Reaction Video".
            # If we swapped, the CONTENT changed, but the label didn't change (my bad in implementation?)
            # Actually, _swap_sources logic swaps widgets. So vid1_label STAYS in vid1_container.
            # So if we swap, vid1_label is nicely sitting above the new content.
            # So showing/hiding it is correct.
            self.is_fullscreen_video = False
        else:
            # Enter Fullscreen
            self.controls_container.hide()
            self.vid1_label.hide()
            self.showFullScreen()
            self.is_fullscreen_video = True

    # ------------------------------------------------
    # Logic
    # ------------------------------------------------
    def _load_file(self, vid_idx):
        path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video Files (*.mp4 *.mkv *.avi *.mov)")
        if not path: return

        if vid_idx == 1:
            self.vid1.load(path)
            # Update master duration logic
            QTimer.singleShot(500, self._refresh_duration)
        else:
            self.vid2.load(path)

    def _refresh_duration(self):
        d = self.vid1.get_duration()
        if d > 0:
            self.duration_video1 = d
            self.slider.setRange(0, int(d * 10))

    def _toggle_play(self):
        self.is_playing = not self.is_playing
        self.btn_play.setText("Pause" if self.is_playing else "Play")
        if self.is_playing:
            self.vid1.play()
            self.vid2.play()
        else:
            self.vid1.pause()
            self.vid2.pause()
            self._sync_anime_pos()

    def _update_offset(self, val):
        self.offset = val
        if not self.is_playing:
            self._sync_anime_pos()

    def _sync_anime_pos(self):
        t1 = self.vid1.get_time()
        t2_target = t1 - self.offset
        self.vid2.seek(t2_target)

    def _update_progress(self):
        if not self._user_seeking and self.is_playing:
            t = self.vid1.get_time()
            self.slider.setValue(int(t * 10))
            
            t2 = self.vid2.get_time()
            target_t2 = t - self.offset
            
            if abs(t2 - target_t2) > 0.5:
                 self.vid2.seek(target_t2)

    def _on_slider_pressed(self):
        self._user_seeking = True
        self.vid1.pause()
        self.vid2.pause()

    def _on_slider_released(self):
        self._user_seeking = False
        val = self.slider.value() / 10.0
        self.vid1.seek(val)
        self.vid2.seek(val - self.offset)
        if self.is_playing:
            self.vid1.play()
            self.vid2.play()

    def _on_slider_move(self, val_int):
        if self._user_seeking:
            val = val_int / 10.0
            self.vid1.seek(val)
            self.vid2.seek(val - self.offset)

    # --- View Logic (Swap & Overlay) ---

    def _swap_sources(self):
        # We want to swap the visual positions of vid1 and vid2.
        # Logic: 
        # 1. Identify which widget is currently 'main' (background) and which is 'secondary' (overlay/window)
        # 2. Swap their parents.
        
        # State tracking:
        # We need to know where they currently are.
        # Case A: Separate Windows
        #   VidA in Main, VidB in Window
        # Case B: Overlay Mode
        #   VidA in Main, VidB in OverlayWrapper
        
        # Simplest way: Check parents
        p1 = self.vid1.parent()
        p2 = self.vid2.parent()
        
        # Helper to get the correct layout/widget to add to
        def get_adder(parent_widget):
            # If parent is DragResizableWidget, user layout()
            # If parent is QWidget container, use layout()
            if parent_widget:
                return parent_widget.layout()
            return None

        # Perform the swap
        # We need to temporarily remove them to avoid "Already has parent" checks firing weirdly or layout issues
        
        # Swap logic is tricky because of the specialized containers (vid1_container vs second_window vs overlay_wrapper)
        # Let's define the "Slots":
        # Slot 1: vid1_container (The main window background)
        # Slot 2: EITHER second_window OR overlay_wrapper (The secondary view)
        
        # Find who occupies Slot 1
        occupant_1 = None
        if self.vid1_container.layout().indexOf(self.vid1) != -1: occupant_1 = self.vid1
        elif self.vid1_container.layout().indexOf(self.vid2) != -1: occupant_1 = self.vid2
        
        # Find who occupies Slot 2
        occupant_2 = None
        # Check overlay first (highest priority if visible)
        if self.overlay_mode:
            # Check content_container layout of drag widget
            cL = self.overlay_wrapper.content_layout
            if cL.indexOf(self.vid1) != -1: occupant_2 = self.vid1
            elif cL.indexOf(self.vid2) != -1: occupant_2 = self.vid2
        else:
            if self.second_window.layout().indexOf(self.vid1) != -1: occupant_2 = self.vid1
            elif self.second_window.layout().indexOf(self.vid2) != -1: occupant_2 = self.vid2

        if not occupant_1 or not occupant_2:
            print("Layout state confusion during swap!")
            return

        # Execute Swap
        # Remove both
        occupant_1.setParent(None)
        occupant_2.setParent(None)
        
        # Add occupant_2 -> Slot 1
        self.vid1_container.layout().addWidget(occupant_2)
        occupant_2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        occupant_2.show()
        
        # Add occupant_1 -> Slot 2
        if self.overlay_mode:
            self.overlay_wrapper.set_content(occupant_1)
        else:
            self.second_window.layout().addWidget(occupant_1)
        occupant_1.show()
        
        # Note: The 'Master' control logic (slider/play) still targets self.vid1 explicitly regardless of view position.
        # This is usually desired (Reaction video stays the master timeline).

    def _toggle_overlay_mode(self, enabled):
        self.overlay_mode = enabled
        
        # Determine who is the "Secondary" content right now
        # It's whoever is NOT in the vid1_container (Main Window Background)
        
        secondary_widget = None
        if self.vid1_container.layout().indexOf(self.vid1) == -1: secondary_widget = self.vid1
        else: secondary_widget = self.vid2
        
        if enabled:
            # Switch to Overlay Mode
            self.second_window.hide()
            
            # Move secondary -> Overlay
            # self.overlay_wrapper is now the DragResizableWidget (QStackedLayout)
            # We use set_content
            self.overlay_wrapper.set_content(secondary_widget)
            secondary_widget.show()
            
            # Show overlay
            self.overlay_wrapper.resize(320, 180)
            self.overlay_wrapper.move(20, 20)
            self.overlay_wrapper.show()
            self.overlay_wrapper.raise_()
            
        else:
            # Switch back to Separate Window Mode
            self.overlay_wrapper.hide()
            
            # Move secondary -> Window
            # But wait, secondary_widget is now child of overlay_wrapper.content_container
            # setParent handles reparenting cleanly
            secondary_widget.setParent(self.second_window)
            self.second_window.layout().addWidget(secondary_widget)
            secondary_widget.show()
            
            self.second_window.show()

    def closeEvent(self, event):
        self.second_window.close()
        super().closeEvent(event)

# -----------------------------------------------------------------------------
# 5. Secondary Window
# -----------------------------------------------------------------------------
class SecondaryWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime Source")
        self.resize(500, 400)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Pre-flight check
    if not check_mpv_available():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Missing MPV Library")
        msg.setText("Could not load 'libmpv'.")
        msg.setInformativeText(
            "Please download libmpv (mpv-2.dll or mpv-1.dll) and place it in this folder:\n"
            f"{os.getcwd()}\n\n"
            "You can download it from: https://sourceforge.net/projects/mpv-player-windows/files/libmpv/"
        )
        msg.exec()
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
