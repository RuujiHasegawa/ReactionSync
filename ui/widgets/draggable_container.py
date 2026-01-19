from PyQt6.QtWidgets import QWidget, QFrame, QStackedLayout, QVBoxLayout
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QMouseEvent
from typing import Optional
from .video_widget import VideoWidget

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
        self.grip.raise_()


class GripWidget(QWidget):
    """Transparent overlay that handles drag/resize logic for its parent."""
    def __init__(self, parent_resizable: QWidget):
        super().__init__(parent_resizable)
        self.target = parent_resizable
        
        # Make this a native window so it sits ON TOP of the MPV native window
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Ensure it behaves as a sub-window without decorations, AND stays on top of the MPV window
        # Fix: Using Tool or Popup might help avoid some "block" issues on some Windows settings,
        # but FramelessWindowHint should be sufficient.
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        self.setMouseTracking(True)
        self.margin = 10
        self._is_moving = False
        self._is_resizing = False
        self._resize_edge: Optional[str] = None
        self._drag_start_pos = QPoint()
        
        # IMPORTANT: "transparent" or "rgba(0,0,0,1)" background with WA_NoSystemBackground.
        # We explicitly set it to transparent.
        self.setStyleSheet("background-color: transparent;")
        
    def paintEvent(self, event):
        # Do not paint anything.
        pass

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
                 if hasattr(widget, "_trigger_fullscreen"):
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
