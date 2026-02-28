"""List model types for MoeGirlTagger image list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt

from apps.pyside.moegirl_tagger_gui_common import DEFAULT_FEATURE_TEXT, normalize_path_key

@dataclass
class ImageListEntry:
    """One list row item."""

    path: Path
    path_key: str
    filename: str
    feature_text: str
    has_existing_tags: bool = False

class ImageListModel(QAbstractListModel):
    """Virtualized model for image list."""

    ROLE_PATH_KEY = Qt.UserRole + 1
    ROLE_FEATURE_TEXT = Qt.UserRole + 2
    ROLE_HAS_EXISTING_TAGS = Qt.UserRole + 3

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize model.

        Args:
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._items: list[ImageListEntry] = []
        self._path_key_to_row: dict[str, int] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return row count.

        Args:
            parent: Parent index.

        Returns:
            Item count.
        """
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """Return row data by role.

        Args:
            index: Row index.
            role: Data role.

        Returns:
            Role data.
        """
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        item = self._items[row]
        if role == Qt.DisplayRole:
            return item.filename
        if role == Qt.ToolTipRole:
            return str(item.path)
        if role == self.ROLE_PATH_KEY:
            return item.path_key
        if role == self.ROLE_FEATURE_TEXT:
            return item.feature_text
        if role == self.ROLE_HAS_EXISTING_TAGS:
            return item.has_existing_tags
        return None

    def set_images(self, images: list[Path]) -> None:
        """Replace all rows with image list.

        Args:
            images: Image path list.
        """
        self.beginResetModel()
        self._items = [
            ImageListEntry(
                path=path,
                path_key=normalize_path_key(path),
                filename=path.name,
                feature_text=DEFAULT_FEATURE_TEXT,
                has_existing_tags=False,
            )
            for path in images
        ]
        self._path_key_to_row = {item.path_key: index for index, item in enumerate(self._items)}
        self.endResetModel()

    def set_feature_by_key(self, path_key: str, feature_text: str) -> None:
        """Update one row feature text by path key.

        Args:
            path_key: Normalized path key.
            feature_text: Updated feature display.
        """
        row = self._path_key_to_row.get(path_key)
        if row is None:
            return
        if self._items[row].feature_text == feature_text:
            return
        self._items[row].feature_text = feature_text
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.ROLE_FEATURE_TEXT])

    def set_existing_tags_by_key(self, path_key: str, feature_text: str, has_existing_tags: bool) -> None:
        """Update one row display and existing-tag flag by path key."""
        row = self._path_key_to_row.get(path_key)
        if row is None:
            return
        changed_roles: list[int] = []
        if self._items[row].feature_text != feature_text:
            self._items[row].feature_text = feature_text
            changed_roles.append(self.ROLE_FEATURE_TEXT)
        if self._items[row].has_existing_tags != has_existing_tags:
            self._items[row].has_existing_tags = has_existing_tags
            changed_roles.append(self.ROLE_HAS_EXISTING_TAGS)
        if not changed_roles:
            return
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, changed_roles)

    def feature_for_key(self, path_key: str) -> str:
        """Get current feature text by path key.

        Args:
            path_key: Normalized path key.

        Returns:
            Current feature text.
        """
        row = self._path_key_to_row.get(path_key)
        if row is None:
            return ""
        return self._items[row].feature_text

    def path_keys_with_existing_tags(self) -> list[str]:
        return [item.path_key for item in self._items if item.has_existing_tags]

    def row_for_key(self, path_key: str) -> int | None:
        return self._path_key_to_row.get(path_key)

    def remove_row(self, row: int) -> str | None:
        if row < 0 or row >= len(self._items):
            return None
        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._items.pop(row)
        self.endRemoveRows()
        self._path_key_to_row = {item.path_key: index for index, item in enumerate(self._items)}
        return removed.path_key

    def remove_by_keys(self, keys: set[str]) -> None:
        if not keys:
            return
        self.beginResetModel()
        self._items = [item for item in self._items if item.path_key not in keys]
        self._path_key_to_row = {item.path_key: index for index, item in enumerate(self._items)}
        self.endResetModel()

    def image_paths(self) -> list[Path]:
        """Return all image paths in current model.

        Returns:
            List of paths.
        """
        return [item.path for item in self._items]
