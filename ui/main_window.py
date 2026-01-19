import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, 
                             QFileDialog, QLabel, QDoubleSpinBox, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer

from core.constants import REFRESH_RATE_MS, SYNC_THRESHOLD_SEC, MIN_WINDOW_SIZE, OVERLAY_DEFAULT_SIZE, OVERLAY_DEFAULT_POS
from ui.widgets.video_widget import VideoWidget, check_mpv_available
from ui.widgets.draggable_container import DragResizableWidget
from ui.secondary_window import SecondaryWindow

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
