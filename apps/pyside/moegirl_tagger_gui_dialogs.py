"""Dialog widgets used by MoeGirlTagger window."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ClearTagsConfirmDialog(QDialog):
    """Project-styled confirmation dialog for clearing image tags."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str,
        confirm_text: str,
        cancel_text: str,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ClearTagsConfirmDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root_layout = QVBoxLayout(self)
        # Keep enough transparent padding so blurred shadow is not clipped.
        root_layout.setContentsMargins(34, 28, 34, 34)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ConfirmDialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("ConfirmDialogTitle")
        title_label.setWordWrap(True)
        message_label = QLabel(message)
        message_label.setObjectName("ConfirmDialogMessage")
        message_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 8, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        confirm_button = QPushButton(confirm_text)
        confirm_button.setObjectName("ConfirmDialogDangerButton")
        confirm_button.clicked.connect(self.accept)
        cancel_button = QPushButton(cancel_text)
        cancel_button.setObjectName("ConfirmDialogSecondaryButton")
        cancel_button.clicked.connect(self.reject)
        confirm_button.setDefault(True)
        confirm_button.setAutoDefault(True)

        button_row.addWidget(confirm_button)
        button_row.addWidget(cancel_button)

        card_layout.addWidget(title_label)
        card_layout.addWidget(message_label)
        card_layout.addLayout(button_row)
        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(54)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(18, 28, 45, 52))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(560)
        self.setStyleSheet(
            """
            QDialog#ClearTagsConfirmDialog { background: transparent; }
            QFrame#ConfirmDialogCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#ConfirmDialogTitle {
                color: #1f2530;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#ConfirmDialogMessage {
                color: #2f3c52;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#ConfirmDialogDangerButton,
            QPushButton#ConfirmDialogSecondaryButton {
                min-width: 98px;
                min-height: 34px;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#ConfirmDialogDangerButton {
                background: #FF6A6A;
                color: #ffffff;
                border: none;
            }
            QPushButton#ConfirmDialogDangerButton:hover { background: #f55f5f; }
            QPushButton#ConfirmDialogDangerButton:pressed { background: #eb5555; }
            QPushButton#ConfirmDialogSecondaryButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#ConfirmDialogSecondaryButton:hover { background: #d4def0; }
            QPushButton#ConfirmDialogSecondaryButton:pressed { background: #c9d6eb; }
            """
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()


class CharacterMergeConfirmDialog(QDialog):
    """Project-styled merge decision dialog for duplicate character import."""

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        message: str,
        candidate_section_title: str,
        candidate_name: str,
        candidate_source: str,
        candidate_links: str,
        candidate_avatar: QPixmap | None,
        existing_section_title: str,
        existing_name: str,
        existing_source: str,
        existing_links: str,
        existing_avatar: QPixmap | None,
        merge_text: str,
        add_new_text: str,
        cancel_text: str,
    ) -> None:
        super().__init__(parent)
        self._decision = "cancel"
        self.setObjectName("CharacterMergeConfirmDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(34, 28, 34, 34)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("CharacterMergeCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("CharacterMergeTitle")
        title_label.setWordWrap(True)
        message_label = QLabel(message)
        message_label.setObjectName("CharacterMergeMessage")
        message_label.setWordWrap(True)

        card_layout.addWidget(title_label)
        card_layout.addWidget(message_label)
        card_layout.addWidget(
            self._build_role_card(
                section_title=candidate_section_title,
                name=candidate_name,
                source=candidate_source,
                links=candidate_links,
                avatar=candidate_avatar,
            )
        )
        card_layout.addWidget(
            self._build_role_card(
                section_title=existing_section_title,
                name=existing_name,
                source=existing_source,
                links=existing_links,
                avatar=existing_avatar,
            )
        )

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 8, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        merge_button = QPushButton(merge_text)
        merge_button.setObjectName("CharacterMergePrimaryButton")
        merge_button.clicked.connect(self._on_merge_clicked)
        merge_button.setDefault(True)
        merge_button.setAutoDefault(True)

        add_new_button = QPushButton(add_new_text)
        add_new_button.setObjectName("CharacterMergeSecondaryButton")
        add_new_button.clicked.connect(self._on_new_clicked)

        cancel_button = QPushButton(cancel_text)
        cancel_button.setObjectName("CharacterMergeSecondaryButton")
        cancel_button.clicked.connect(self._on_cancel_clicked)

        button_row.addWidget(merge_button)
        button_row.addWidget(add_new_button)
        button_row.addWidget(cancel_button)
        card_layout.addLayout(button_row)

        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(54)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(18, 28, 45, 52))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(700)
        self.setStyleSheet(
            """
            QDialog#CharacterMergeConfirmDialog { background: transparent; }
            QFrame#CharacterMergeCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#CharacterMergeTitle {
                color: #1f2530;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#CharacterMergeMessage {
                color: #2f3c52;
                font-size: 13px;
                font-weight: 500;
            }
            QFrame#CharacterMergeRoleCard {
                background: #f8fbff;
                border: 1px solid #dbe5f5;
                border-radius: 12px;
            }
            QLabel#CharacterMergeRoleTitle {
                color: #273247;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#CharacterMergeRoleName {
                color: #1f2530;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#CharacterMergeRoleSubtitle {
                color: #51627e;
                font-size: 12px;
                font-weight: 500;
            }
            QLabel#CharacterMergeAvatar {
                background: #eef3fb;
                border: 1px solid #d6e0f0;
                border-radius: 10px;
            }
            QPushButton#CharacterMergePrimaryButton,
            QPushButton#CharacterMergeSecondaryButton {
                min-width: 98px;
                min-height: 34px;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#CharacterMergePrimaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
                color: #ffffff;
                border: none;
            }
            QPushButton#CharacterMergePrimaryButton:hover { background: #1f70f3; }
            QPushButton#CharacterMergePrimaryButton:pressed { background: #135fdb; }
            QPushButton#CharacterMergeSecondaryButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#CharacterMergeSecondaryButton:hover { background: #d4def0; }
            QPushButton#CharacterMergeSecondaryButton:pressed { background: #c9d6eb; }
            """
        )

    def _build_role_card(
        self,
        *,
        section_title: str,
        name: str,
        source: str,
        links: str,
        avatar: QPixmap | None,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("CharacterMergeRoleCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        avatar_label = QLabel()
        avatar_label.setObjectName("CharacterMergeAvatar")
        avatar_label.setAlignment(Qt.AlignCenter)
        avatar_label.setFixedSize(58, 58)
        if isinstance(avatar, QPixmap) and not avatar.isNull():
            avatar_label.setProperty("hasAvatar", True)
            avatar_label.setPixmap(self._rounded_avatar_pixmap(avatar, 56, 9))
        else:
            avatar_label.setProperty("hasAvatar", False)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)

        section_label = QLabel(section_title)
        section_label.setObjectName("CharacterMergeRoleTitle")
        name_label = QLabel(name)
        name_label.setObjectName("CharacterMergeRoleName")
        name_label.setWordWrap(True)
        source_label = QLabel(source)
        source_label.setObjectName("CharacterMergeRoleSubtitle")
        source_label.setWordWrap(True)
        links_label = QLabel(links)
        links_label.setObjectName("CharacterMergeRoleSubtitle")
        links_label.setWordWrap(True)

        text_column.addWidget(section_label)
        text_column.addWidget(name_label)
        text_column.addWidget(source_label)
        text_column.addWidget(links_label)

        layout.addWidget(avatar_label)
        layout.addLayout(text_column, 1)
        return card

    def _on_merge_clicked(self) -> None:
        self._decision = "merge"
        self.accept()

    def _on_new_clicked(self) -> None:
        self._decision = "new"
        self.accept()

    def _on_cancel_clicked(self) -> None:
        self._decision = "cancel"
        self.reject()

    def decision(self) -> str:
        return self._decision

    @staticmethod
    def _rounded_avatar_pixmap(source: QPixmap, size: int, radius: int) -> QPixmap:
        """Render avatar as rounded square pixmap to match list icon style."""
        side = max(1, int(size))
        corner = max(0, int(radius))
        scaled = source.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        cropped = scaled.copy(
            max(0, (scaled.width() - side) // 2),
            max(0, (scaled.height() - side) // 2),
            side,
            side,
        )

        output = QPixmap(side, side)
        output.fill(Qt.transparent)
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0, 0, side, side, corner, corner)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()
        return output

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()
