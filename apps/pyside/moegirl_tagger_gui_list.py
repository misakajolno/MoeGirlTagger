"""List view and delegate rendering for MoeGirlTagger image list."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from apps.pyside.moegirl_tagger_gui_common import (
    DELETE_BUTTON_MARGIN,
    DELETE_BUTTON_SIZE,
    compute_delete_button_rect,
    compute_delete_hit_rect,
    compute_row_rect,
    load_list_delete_icon,
    SHOW_DELETE_HITBOX,
)
from apps.pyside.moegirl_tagger_gui_model import ImageListModel

class ImageListView(QListView):
    """ListView that supports per-row delete button click."""

    deleteRequested = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._consume_next_release = False

    def _delete_path_key_at(self, pos: QPoint) -> str:
        index = self.indexAt(pos)
        if not index.isValid():
            return ""

        item_rect = self.visualRect(index)
        if not item_rect.contains(pos):
            return ""
        delete_hit_rect = compute_delete_hit_rect(item_rect)
        if not delete_hit_rect.contains(pos):
            return ""
        return str(index.data(ImageListModel.ROLE_PATH_KEY) or "")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            path_key = self._delete_path_key_at(event.position().toPoint())
            if path_key:
                self.deleteRequested.emit(path_key)
                self._consume_next_release = True
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._consume_next_release and event.button() == Qt.LeftButton:
            self._consume_next_release = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

class ImageListDelegate(QStyledItemDelegate):
    """Custom row renderer for virtualized list."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize delegate.

        Args:
            parent: Parent object.
        """
        super().__init__(parent)
        self._title_font = QFont()
        self._title_font.setPointSize(12)
        self._title_font.setWeight(QFont.DemiBold)
        self._subtitle_font = QFont()
        self._subtitle_font.setPointSize(10)
        self._delete_icon = load_list_delete_icon() or QIcon()
        self._delete_icon_size = 24
        self._delete_button_has_background = False

    def sizeHint(self, option, index) -> QSize:
        """Return fixed row size.

        Args:
            option: View option.
            index: Model index.

        Returns:
            Row size.
        """
        _ = option
        _ = index
        return QSize(760, 76)

    def paint(self, painter: QPainter, option, index) -> None:
        """Paint one row item.

        Args:
            painter: Painter object.
            option: View style option.
            index: Model index.
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        item_rect = option.rect
        row_rect = compute_row_rect(item_rect)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        background_color = QColor("#f8faff")
        border_color = QColor(0, 0, 0, 0)
        if hovered:
            background_color = QColor("#eef4ff")
            border_color = QColor("#d3e2ff")
        if selected:
            background_color = QColor("#e8f1ff")
            border_color = QColor("#bcd1ff")

        background_path = QPainterPath()
        background_path.addRoundedRect(QRectF(row_rect), 12, 12)
        painter.fillPath(background_path, background_color)
        painter.setPen(border_color)
        painter.drawPath(background_path)

        title = str(index.data(Qt.DisplayRole) or "")
        subtitle = str(index.data(ImageListModel.ROLE_FEATURE_TEXT) or "")

        inner_rect = row_rect.adjusted(12, 4, -12, -4)
        gap = 2
        line_height = max(1, (inner_rect.height() - gap) // 2)
        reserved_right = DELETE_BUTTON_SIZE + DELETE_BUTTON_MARGIN + 6
        text_rect = inner_rect.adjusted(0, 0, -reserved_right, 0)
        title_rect = text_rect.adjusted(0, 0, 0, -(text_rect.height() - line_height))
        subtitle_rect = text_rect.adjusted(0, line_height + gap, 0, 0)

        painter.setFont(self._title_font)
        title_text = painter.fontMetrics().elidedText(title, Qt.ElideRight, title_rect.width())
        painter.setPen(QColor("#1d2430"))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title_text)

        painter.setFont(self._subtitle_font)
        painter.setPen(QColor("#6b778a"))
        self._draw_subtitle_chips(painter, subtitle_rect, subtitle)
        delete_rect = QRect(compute_delete_button_rect(item_rect))
        self._draw_delete_button(painter, delete_rect, hovered)
        if SHOW_DELETE_HITBOX:
            self._draw_delete_hitbox(painter, QRect(compute_delete_hit_rect(item_rect)))
        painter.restore()

    def _draw_delete_button(self, painter: QPainter, rect: QRect, hovered: bool) -> None:
        painter.save()
        _ = hovered
        if not self._delete_icon.isNull():
            icon_size = min(self._delete_icon_size, rect.width(), rect.height())
            icon_pixmap = self._delete_icon.pixmap(icon_size, icon_size)
            icon_rect = QRect(0, 0, icon_size, icon_size)
            icon_rect.moveCenter(rect.center())
            painter.drawPixmap(icon_rect, icon_pixmap)
        else:
            painter.setPen(QColor("#6b778a"))
            painter.setFont(self._subtitle_font)
            painter.drawText(QRectF(rect), Qt.AlignCenter, "✕")
        painter.restore()

    def _draw_delete_hitbox(self, painter: QPainter, rect: QRect) -> None:
        painter.save()
        painter.setBrush(QColor(255, 106, 106, 24))
        painter.setPen(QColor(255, 106, 106, 150))
        painter.drawRoundedRect(QRectF(rect), 8, 8)
        painter.restore()

    def _draw_subtitle_chips(self, painter: QPainter, rect, subtitle: str) -> None:
        subtitle = subtitle.strip()
        if not subtitle:
            return

        metrics = painter.fontMetrics()
        chip_padding_x = 8
        chip_padding_y = 2
        chip_height = metrics.height() + chip_padding_y * 2
        chip_radius = chip_height // 2
        x = rect.left()
        y = rect.top() + max(0, (rect.height() - chip_height) // 2)
        available_right = rect.right()

        sections = self._parse_subtitle_sections(subtitle)
        if not sections:
            sections = [(None, [subtitle])]

        for section_index, (prefix, tags) in enumerate(sections):
            if prefix:
                prefix_text = prefix + " "
                prefix_width = metrics.horizontalAdvance(prefix_text)
                if x + prefix_width > available_right:
                    return
                painter.drawText(
                    QRectF(x, rect.top(), prefix_width, rect.height()),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    prefix_text,
                )
                x += prefix_width

            for tag in tags:
                if not tag:
                    continue
                tag_width = metrics.horizontalAdvance(tag)
                chip_width = tag_width + chip_padding_x * 2
                if x + chip_width > available_right:
                    overflow_text = "…"
                    overflow_width = metrics.horizontalAdvance(overflow_text) + chip_padding_x * 2
                    if x + overflow_width <= available_right:
                        chip_rect = QRectF(x, y, overflow_width, chip_height)
                        path = QPainterPath()
                        path.addRoundedRect(chip_rect, chip_radius, chip_radius)
                        painter.fillPath(path, QColor("#edf2fb"))
                        painter.setPen(QColor("#6b778a"))
                        painter.drawText(chip_rect, Qt.AlignCenter, overflow_text)
                    return

                chip_rect = QRectF(x, y, chip_width, chip_height)
                path = QPainterPath()
                path.addRoundedRect(chip_rect, chip_radius, chip_radius)
                painter.fillPath(path, QColor("#edf2fb"))
                painter.setPen(QColor("#6b778a"))
                painter.drawText(chip_rect, Qt.AlignCenter, tag)
                x += chip_width + 6

            if section_index < len(sections) - 1:
                x += 6

    def _parse_subtitle_sections(self, subtitle: str) -> list[tuple[str | None, list[str]]]:
        parts = [part.strip() for part in subtitle.replace(";", "；").split("；") if part.strip()]
        if not parts:
            return []

        result: list[tuple[str | None, list[str]]] = []
        for part in parts:
            if "：" in part:
                prefix, content = part.split("：", 1)
                tags = [tag.strip() for tag in content.replace("，", "、").replace(",", "、").split("、") if tag.strip()]
                result.append((prefix.strip() + "：", tags))
                continue
            if ":" in part:
                prefix, content = part.split(":", 1)
                tags = [tag.strip() for tag in content.replace("，", "、").replace(",", "、").split("、") if tag.strip()]
                result.append((prefix.strip() + ":", tags))
                continue
            tags = [tag.strip() for tag in part.replace("，", "、").replace(",", "、").split("、") if tag.strip()]
            result.append((None, tags))
        return result
