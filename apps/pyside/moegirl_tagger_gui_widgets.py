"""Reusable GUI widgets for MoeGirlTagger window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from apps.pyside.moegirl_tagger_gui_common import load_window_close_icon


class CapsuleSwitch(QCheckBox):
    """Compact capsule-style on/off switch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("")
        self.setCursor(Qt.PointingHandCursor)
        self._switch_size = QSize(59, 31)
        self.setFixedSize(self._switch_size)
        self.setTristate(False)

    def sizeHint(self) -> QSize:
        return QSize(self._switch_size)

    def minimumSizeHint(self) -> QSize:
        return QSize(self._switch_size)

    def hitButton(self, pos: QPoint) -> bool:
        """Allow clicking anywhere on the capsule to toggle state."""
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        track_rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        checked = self.isChecked()
        enabled = self.isEnabled()

        if checked:
            track_fill = QColor("#4ed689") if enabled else QColor("#8ad9ae")
            track_border = QColor("#44c57b") if enabled else QColor("#7ac7a0")
        else:
            track_fill = QColor("#d8deea") if enabled else QColor("#e4e8f0")
            track_border = QColor("#c5cfdf") if enabled else QColor("#d5dbe6")

        painter.setPen(track_border)
        painter.setBrush(track_fill)
        radius = track_rect.height() / 2.0
        painter.drawRoundedRect(track_rect, radius, radius)

        margin = 2.5
        thumb_diameter = track_rect.height() - margin * 2.0
        if checked:
            thumb_x = track_rect.right() - margin - thumb_diameter
        else:
            thumb_x = track_rect.left() + margin
        thumb_rect = QRectF(thumb_x, track_rect.top() + margin, thumb_diameter, thumb_diameter)

        painter.setPen(QColor(0, 0, 0, 18))
        painter.setBrush(QColor("#ffffff") if enabled else QColor("#f5f7fb"))
        painter.drawEllipse(thumb_rect)

class PreviewCanvas(QWidget):
    """Rounded preview canvas with centered fit rendering."""

    def __init__(self, placeholder_text: str) -> None:
        """Initialize preview canvas.

        Args:
            placeholder_text: Default placeholder text.
        """
        super().__init__()
        self.setObjectName("PreviewLabel")
        self._placeholder_text = placeholder_text
        self._pixmap: QPixmap | None = None
        self._corner_radius = 16.0

    def set_placeholder(self, text: str) -> None:
        """Set placeholder and clear current pixmap.

        Args:
            text: Placeholder message.
        """
        self._placeholder_text = text
        self._pixmap = None
        self.update()

    def set_image_path(self, image_path: Path) -> bool:
        """Load image from path.

        Args:
            image_path: Source image path.

        Returns:
            Whether image loaded successfully.
        """
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self._pixmap = None
            self.update()
            return False
        self._pixmap = pixmap
        self.update()
        return True

    def paintEvent(self, event) -> None:
        """Render image with rounded clipping and centered fit.

        Args:
            event: Paint event.
        """
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._corner_radius, self._corner_radius)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), Qt.transparent)

        if self._pixmap is None or self._pixmap.isNull():
            painter.fillRect(self.rect(), Qt.transparent)
            painter.setPen(QColor("#758094"))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder_text)
            return

        scaled = self._pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        scaled_width = scaled.width() / max(1.0, scaled.devicePixelRatio())
        scaled_height = scaled.height() / max(1.0, scaled.devicePixelRatio())
        target_rect = QRectF(0, 0, scaled_width, scaled_height)
        target_rect.moveCenter(rect.center())
        painter.drawPixmap(target_rect.toRect(), scaled)

class DragBar(QFrame):
    """Frameless drag bar with custom window control buttons."""

    def __init__(self, parent: QWidget) -> None:
        """Initialize drag bar.

        Args:
            parent: Parent window.
        """
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self.setObjectName("DragBar")
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 6, 2)
        layout.setSpacing(6)

        self.caption = QLabel("MoeGirlTagger")
        self.caption.setObjectName("CaptionLabel")
        caption_font = QFont()
        caption_font.setPointSize(10)
        self.caption.setFont(caption_font)
        self.caption.hide()
        layout.addStretch(1)

        self.min_btn = QPushButton("—")
        self.close_btn = QPushButton("✕")
        for button in (self.min_btn, self.close_btn):
            button.setObjectName("WindowButton")
            button.setFixedSize(QSize(34, 26))
            layout.addWidget(button)

        close_icon = load_window_close_icon()
        if close_icon is not None and not close_icon.isNull():
            self.close_btn.setText("")
            self.close_btn.setIcon(close_icon)
            self.close_btn.setIconSize(QSize(14, 14))

        self.min_btn.clicked.connect(self.window().showMinimized)
        self.close_btn.clicked.connect(self.window().close)

    def mousePressEvent(self, event) -> None:
        """Start window drag.

        Args:
            event: Mouse event.
        """
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Move window while dragging.

        Args:
            event: Mouse event.
        """
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            if self.window().isMaximized():
                self.window().showNormal()
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Stop dragging.

        Args:
            event: Mouse event.
        """
        self._drag_offset = None
        super().mouseReleaseEvent(event)
