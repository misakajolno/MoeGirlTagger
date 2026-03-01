"""UI construction and settings behavior mixin for MoeGirlTagger window."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from apps.pyside.moegirl_tagger_gui_common import (
    DEFAULT_LANGUAGE,
    DEFAULT_THRESHOLDS,
    LANGUAGE_OPTIONS,
    LANGUAGE_SETTING_KEY,
    SPIN_DOWN_ICON_PATH,
    SPIN_UP_ICON_PATH,
    THRESHOLD_LABEL_KEYS,
    THRESHOLD_MAX_VALUE,
    THRESHOLD_MIN_VALUE,
    THRESHOLD_SETTING_KEYS,
    TRANSLATIONS,
    clamp_threshold,
    normalize_language_code,
)
from apps.pyside.moegirl_tagger_gui_list import ImageListDelegate, ImageListView
from apps.pyside.moegirl_tagger_gui_styles import build_window_qss
from apps.pyside.moegirl_tagger_gui_workers import CorrelationProfileRebuildWorker
from apps.pyside.moegirl_tagger_gui_widgets import DragBar, PreviewCanvas


class MoeGirlTaggerWindowUiMixin:
    """Build and style window pages."""

    def _init_ui(self) -> None:
        """Build window widgets and layouts."""
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 0, 18, 18)
        root_layout.setSpacing(0)

        self.window_frame = QFrame()
        self.window_frame.setObjectName("WindowFrame")
        frame_layout = QVBoxLayout(self.window_frame)
        frame_layout.setContentsMargins(18, 0, 18, 18)
        frame_layout.setSpacing(0)

        self.drag_bar = DragBar(self)
        frame_layout.addWidget(self.drag_bar)
        frame_layout.addSpacing(10)

        self.analysis_menu_button = QPushButton()
        self.analysis_menu_button.setObjectName("SideMenuButton")
        self.analysis_menu_button.setCheckable(True)
        self.analysis_menu_button.setFixedSize(60, 60)
        self.analysis_menu_button.setIconSize(QSize(30, 30))
        self.character_menu_button = QPushButton()
        self.character_menu_button.setObjectName("SideMenuButton")
        self.character_menu_button.setCheckable(True)
        self.character_menu_button.setFixedSize(60, 60)
        self.character_menu_button.setIconSize(QSize(30, 30))
        self.settings_menu_button = QPushButton()
        self.settings_menu_button.setObjectName("SideMenuButton")
        self.settings_menu_button.setCheckable(True)
        self.settings_menu_button.setFixedSize(60, 60)
        self.settings_menu_button.setIconSize(QSize(30, 30))

        side_menu_panel = QFrame()
        side_menu_panel.setObjectName("SideMenuPanel")
        side_menu_panel.setFixedWidth(80)
        side_menu_layout = QVBoxLayout(side_menu_panel)
        side_menu_layout.setContentsMargins(10, 10, 10, 10)
        side_menu_layout.setSpacing(8)
        side_menu_layout.addWidget(self.analysis_menu_button, 0, Qt.AlignHCenter)
        side_menu_layout.addWidget(self.character_menu_button, 0, Qt.AlignHCenter)
        side_menu_layout.addWidget(self.settings_menu_button, 0, Qt.AlignHCenter)
        side_menu_layout.addStretch(1)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("MainPageStack")
        self.page_stack.addWidget(self._build_analysis_page())
        self.page_stack.addWidget(self._build_character_page())
        self.page_stack.addWidget(self._build_settings_page())

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(side_menu_panel, 0)
        content_layout.addWidget(self.page_stack, 1)
        frame_layout.addLayout(content_layout, 1)

        root_layout.addWidget(self.window_frame, 1)
        self.setCentralWidget(root)

        self.folder_button.clicked.connect(self._choose_folder)
        self.images_button.clicked.connect(self._choose_images)
        self.remove_all_button.clicked.connect(self._remove_all_images)
        self.clear_tags_button.clicked.connect(self._clear_tagged_images)
        self.remove_tagged_button.clicked.connect(self._remove_tagged_images)
        self.start_button.clicked.connect(self._start_analysis)
        self.analysis_menu_button.clicked.connect(lambda _checked=False: self._switch_right_page(0))
        self.character_menu_button.clicked.connect(lambda _checked=False: self._switch_right_page(1))
        self.settings_menu_button.clicked.connect(lambda _checked=False: self._switch_right_page(2))
        self.list_widget.selectionModel().currentChanged.connect(self._on_current_item_changed)
        self.list_widget.deleteRequested.connect(self._delete_image_by_key)
        self.character_search_button.clicked.connect(self._search_characters_online)
        self.character_library_search_button.clicked.connect(self._start_character_library_search)
        self.character_library_search_input.returnPressed.connect(self._start_character_library_search)
        self.character_bulk_button.clicked.connect(self._start_bulk_character_build)
        self.character_import_button.clicked.connect(self._import_selected_character)
        self.character_delete_button.clicked.connect(self._request_delete_selected_character)
        self.character_add_refs_button.clicked.connect(self._append_selected_character_references)
        self.character_refresh_button.clicked.connect(self._reload_character_library_list)

        self._switch_right_page(0)
        self._reload_character_library_list()
        self.remove_all_button.hide()
        self.clear_tags_button.hide()
        self.remove_tagged_button.hide()

    def _build_analysis_page(self) -> QWidget:
        """Create analysis workspace page."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)

        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls_layout = QHBoxLayout(controls_card)
        controls_layout.setContentsMargins(16, 12, 16, 12)
        controls_layout.setSpacing(12)

        self.folder_button = QPushButton()
        self.folder_button.setObjectName("SecondaryButton")
        self.images_button = QPushButton()
        self.images_button.setObjectName("SecondaryButton")
        self.remove_all_button = QPushButton()
        self.remove_all_button.setObjectName("DangerButton")
        self.clear_tags_button = QPushButton()
        self.clear_tags_button.setObjectName("SecondaryButton")
        self.remove_tagged_button = QPushButton()
        self.remove_tagged_button.setObjectName("DangerButton")
        self.start_button = QPushButton()
        self.start_button.setObjectName("PrimaryButton")
        self.count_label = QLabel()
        self.count_label.setObjectName("CountLabel")
        self.folder_button.setFixedHeight(38)
        self.images_button.setFixedHeight(38)
        self.remove_all_button.setFixedHeight(38)
        self.clear_tags_button.setFixedHeight(38)
        self.remove_tagged_button.setFixedHeight(38)
        self.start_button.setFixedHeight(38)

        controls_layout.addWidget(self.folder_button)
        controls_layout.addWidget(self.images_button)
        controls_layout.addWidget(self.count_label)
        controls_layout.addStretch(1)
        controls_layout.addWidget(self.clear_tags_button)
        controls_layout.addWidget(self.remove_all_button)
        controls_layout.addWidget(self.remove_tagged_button)
        controls_layout.addWidget(self.start_button)
        page_layout.addWidget(controls_card)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)

        left_card = QFrame()
        left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.preview_label = PreviewCanvas(self._tr("preview_placeholder"))
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout.addWidget(self.preview_label, 1)

        right_card = QFrame()
        right_card.setObjectName("Card")
        right_card.setFixedWidth(790)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(8)

        self.list_widget = ImageListView()
        self.list_widget.setObjectName("ImageList")
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSelectionMode(QListView.SingleSelection)
        self.list_widget.setEditTriggers(QListView.NoEditTriggers)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(6)
        self.list_widget.setModel(self.image_model)
        self.list_widget.setItemDelegate(ImageListDelegate(self.list_widget))

        self.status_label = QLabel()
        self.status_label.setObjectName("StatusLabel")
        right_layout.addWidget(self.list_widget, 1)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(left_card)
        splitter.addWidget(right_card)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([1080, 790])
        page_layout.addWidget(splitter, 1)
        return page

    def _build_character_page(self) -> QWidget:
        """Create character management page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)
        layout.addWidget(card, 1)

        self.character_page_title_label = QLabel()
        self.character_page_title_label.setObjectName("SettingsTitle")
        card_layout.addWidget(self.character_page_title_label)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)
        self.character_search_input = QLineEdit()
        self.character_search_input.setObjectName("CharacterSearchInput")
        self.character_search_button = QPushButton()
        self.character_search_button.setObjectName("PrimaryButton")
        self.character_library_search_input = QLineEdit()
        self.character_library_search_input.setObjectName("CharacterSearchInput")
        self.character_library_search_button = QPushButton()
        self.character_library_search_button.setObjectName("SecondaryButton")
        search_row.addWidget(self.character_search_input, 1)
        search_row.addWidget(self.character_search_button, 0)
        search_row.addWidget(self.character_library_search_input, 1)
        search_row.addWidget(self.character_library_search_button, 0)
        card_layout.addLayout(search_row)

        bulk_row = QHBoxLayout()
        bulk_row.setContentsMargins(0, 0, 0, 0)
        bulk_row.setSpacing(8)
        self.character_bulk_label = QLabel()
        self.character_bulk_label.setObjectName("SettingsHint")
        self.character_bulk_count_spin = QSpinBox()
        self.character_bulk_count_spin.setObjectName("ThresholdInput")
        self.character_bulk_count_spin.setRange(1, 10)
        self.character_bulk_count_spin.setSingleStep(1)
        self.character_bulk_count_spin.setValue(5)
        self.character_bulk_count_spin.setFixedWidth(110)
        self.character_bulk_button = QPushButton()
        self.character_bulk_button.setObjectName("PrimaryButton")
        bulk_row.addWidget(self.character_bulk_label)
        bulk_row.addWidget(self.character_bulk_count_spin, 0)
        bulk_row.addWidget(self.character_bulk_button, 0)
        bulk_row.addStretch(1)
        card_layout.addLayout(bulk_row)
        self.character_bulk_progress = QProgressBar()
        self.character_bulk_progress.setObjectName("CharacterBulkProgress")
        self.character_bulk_progress.setTextVisible(True)
        self.character_bulk_progress.setFixedHeight(18)
        card_layout.addWidget(self.character_bulk_progress)
        self._reset_character_bulk_progress()

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)
        self.character_import_button = QPushButton()
        self.character_import_button.setObjectName("PrimaryButton")
        self.character_add_refs_button = QPushButton()
        self.character_add_refs_button.setObjectName("SecondaryButton")
        self.character_delete_button = QPushButton()
        self.character_delete_button.setObjectName("DangerButton")
        self.character_refresh_button = QPushButton()
        self.character_refresh_button.setObjectName("SecondaryButton")
        actions_row.addWidget(self.character_import_button)
        actions_row.addWidget(self.character_refresh_button)
        actions_row.addStretch(1)
        actions_row.addWidget(self.character_add_refs_button)
        actions_row.addWidget(self.character_delete_button)
        card_layout.addLayout(actions_row)

        list_splitter = QSplitter(Qt.Horizontal)
        list_splitter.setChildrenCollapsible(False)
        list_splitter.setHandleWidth(10)

        search_card = QFrame()
        search_card.setObjectName("Card")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(12, 12, 12, 12)
        search_layout.setSpacing(6)
        self.character_search_results_label = QLabel()
        self.character_search_results_label.setObjectName("SettingsSectionTitle")
        self.character_search_list = QListWidget()
        self.character_search_list.setObjectName("CharacterSearchList")
        self.character_search_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.character_search_list.setIconSize(QSize(46, 46))
        self.character_search_list.setSpacing(2)
        search_layout.addWidget(self.character_search_results_label)
        search_layout.addWidget(self.character_search_list, 1)
        self.character_search_select_all_shortcut = QShortcut(QKeySequence.SelectAll, self.character_search_list)
        self.character_search_select_all_shortcut.activated.connect(self.character_search_list.selectAll)

        local_card = QFrame()
        local_card.setObjectName("Card")
        local_layout = QVBoxLayout(local_card)
        local_layout.setContentsMargins(12, 12, 12, 12)
        local_layout.setSpacing(6)
        self.character_library_label = QLabel()
        self.character_library_label.setObjectName("SettingsSectionTitle")
        self.character_library_list = QListWidget()
        self.character_library_list.setObjectName("CharacterLibraryList")
        self.character_library_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.character_library_list.setIconSize(QSize(46, 46))
        self.character_library_list.setSpacing(2)
        local_layout.addWidget(self.character_library_label)
        local_layout.addWidget(self.character_library_list, 1)
        self.character_library_select_all_shortcut = QShortcut(QKeySequence.SelectAll, self.character_library_list)
        self.character_library_select_all_shortcut.activated.connect(self.character_library_list.selectAll)
        self.character_library_delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.character_library_list)
        self.character_library_delete_shortcut.activated.connect(self._request_delete_selected_character)
        self.character_library_delete_fast_shortcut = QShortcut(
            QKeySequence("Ctrl+Delete"),
            self.character_library_list,
        )
        self.character_library_delete_fast_shortcut.activated.connect(self._quick_delete_selected_character)

        list_splitter.addWidget(search_card)
        list_splitter.addWidget(local_card)
        list_splitter.setStretchFactor(0, 1)
        list_splitter.setStretchFactor(1, 1)
        list_splitter.setSizes([620, 620])
        card_layout.addWidget(list_splitter, 1)

        return page

    def _build_settings_page(self) -> QWidget:
        """Create settings page widget."""
        page = QWidget()
        outer_layout = QVBoxLayout(page)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        outer_layout.addWidget(card, 1)

        self.settings_title_label = QLabel()
        self.settings_title_label.setObjectName("SettingsTitle")
        self.settings_subtitle_label = QLabel()
        self.settings_subtitle_label.setObjectName("SettingsSubtitle")
        self.settings_subtitle_label.setWordWrap(True)

        self.settings_range_hint_label = QLabel()
        self.settings_range_hint_label.setObjectName("SettingsHint")
        self.settings_range_hint_label.setWordWrap(True)
        self.settings_diff_hint_label = QLabel()
        self.settings_diff_hint_label.setObjectName("SettingsHint")
        self.settings_diff_hint_label.setWordWrap(True)
        self.settings_threshold_note_label = QLabel()
        self.settings_threshold_note_label.setObjectName("SettingsHint")
        self.settings_threshold_note_label.setWordWrap(True)

        layout.addWidget(self.settings_title_label)

        self.language_title_label = QLabel()
        self.language_title_label.setObjectName("SettingsSectionTitle")
        layout.addWidget(self.language_title_label)

        language_layout = QHBoxLayout()
        language_layout.setContentsMargins(0, 0, 0, 0)
        language_layout.setSpacing(8)
        self.language_group = QButtonGroup(self)
        self.language_group.setExclusive(True)
        for code, button_name in LANGUAGE_OPTIONS:
            button = QPushButton(button_name)
            button.setObjectName("LanguageButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _, lang_code=code: self._on_language_switched(lang_code))
            self.language_group.addButton(button)
            self.language_buttons[code] = button
            language_layout.addWidget(button)
        language_layout.addStretch(1)
        layout.addLayout(language_layout)
        layout.addSpacing(10)

        self.threshold_title_label = QLabel()
        self.threshold_title_label.setObjectName("SettingsSectionTitle")
        layout.addWidget(self.threshold_title_label)
        layout.addWidget(self.settings_range_hint_label)
        layout.addWidget(self.settings_diff_hint_label)
        layout.addWidget(self.settings_threshold_note_label)

        threshold_grid = QGridLayout()
        threshold_grid.setContentsMargins(0, 0, 0, 0)
        threshold_grid.setHorizontalSpacing(10)
        threshold_grid.setVerticalSpacing(8)
        for row, key in enumerate(DEFAULT_THRESHOLDS):
            name_label = QLabel()
            name_label.setObjectName("ThresholdName")
            input_box = QDoubleSpinBox()
            input_box.setObjectName("ThresholdInput")
            input_box.setDecimals(2)
            input_box.setSingleStep(0.01)
            input_box.setRange(THRESHOLD_MIN_VALUE, THRESHOLD_MAX_VALUE)
            input_box.setKeyboardTracking(False)
            input_box.setMinimumWidth(130)
            range_label = QLabel()
            range_label.setObjectName("ThresholdRange")

            threshold_grid.addWidget(name_label, row, 0)
            threshold_grid.addWidget(input_box, row, 1)
            threshold_grid.addWidget(range_label, row, 2)

            self.threshold_name_labels[key] = name_label
            self.threshold_inputs[key] = input_box
            self.threshold_range_labels[key] = range_label
        threshold_grid.setColumnStretch(0, 3)
        threshold_grid.setColumnStretch(1, 1)
        threshold_grid.setColumnStretch(2, 2)
        layout.addLayout(threshold_grid)
        layout.addWidget(self.settings_subtitle_label)

        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 4, 0, 0)
        action_layout.setSpacing(10)
        self.reset_settings_button = QPushButton()
        self.reset_settings_button.setObjectName("SecondaryButton")
        self.reset_settings_button.clicked.connect(self._reset_threshold_inputs)
        self.save_settings_button = QPushButton()
        self.save_settings_button.setObjectName("PrimaryButton")
        self.save_settings_button.clicked.connect(self._save_threshold_settings)
        action_layout.addWidget(self.reset_settings_button)
        action_layout.addWidget(self.save_settings_button)
        action_layout.addStretch(1)
        layout.addLayout(action_layout)

        self.rebuild_correlation_profiles_button = QPushButton()
        self.rebuild_correlation_profiles_button.setObjectName("SecondaryButton")
        self.rebuild_correlation_profiles_button.clicked.connect(self._start_rebuild_correlation_profiles)
        layout.addWidget(self.rebuild_correlation_profiles_button, 0, Qt.AlignLeft)

        self.rebuild_correlation_profiles_hint_label = QLabel()
        self.rebuild_correlation_profiles_hint_label.setObjectName("SettingsHint")
        self.rebuild_correlation_profiles_hint_label.setWordWrap(True)
        layout.addWidget(self.rebuild_correlation_profiles_hint_label)

        self.toast_label = QLabel()
        self.toast_label.setObjectName("ToastLabel")
        self.toast_label.hide()
        layout.addWidget(self.toast_label, 0, Qt.AlignRight)
        layout.addStretch(1)

        return page

    def _switch_right_page(self, page_index: int) -> None:
        """Switch right panel page."""
        self.page_stack.setCurrentIndex(page_index)
        self.analysis_menu_button.setChecked(page_index == 0)
        self.character_menu_button.setChecked(page_index == 1)
        self.settings_menu_button.setChecked(page_index == 2)
        self._update_side_menu_icons()

    def _update_side_menu_icons(self) -> None:
        """Apply selected/unselected icon for side menu buttons."""
        analysis_icon = (
            self.analysis_menu_selected_icon if self.analysis_menu_button.isChecked() else self.analysis_menu_default_icon
        )
        character_icon = (
            self.character_menu_selected_icon if self.character_menu_button.isChecked() else self.character_menu_default_icon
        )
        settings_icon = (
            self.settings_menu_selected_icon if self.settings_menu_button.isChecked() else self.settings_menu_default_icon
        )
        self.analysis_menu_button.setIcon(analysis_icon)
        self.character_menu_button.setIcon(character_icon)
        self.settings_menu_button.setIcon(settings_icon)

    def _on_language_switched(self, language_code: str) -> None:
        """Apply language switch and persist selection."""
        normalized = normalize_language_code(language_code)
        if normalized == self.current_language:
            self.language_buttons[normalized].setChecked(True)
            return
        self.current_language = normalized
        self.settings.setValue(LANGUAGE_SETTING_KEY, normalized)
        if hasattr(self, "_refresh_taxonomy_name_map"):
            self._refresh_taxonomy_name_map()
        self._apply_language()

    def _sync_threshold_inputs(self) -> None:
        """Sync threshold controls with persisted values."""
        for key, spinbox in self.threshold_inputs.items():
            spinbox.setValue(self.threshold_values.get(key, DEFAULT_THRESHOLDS[key]))

    def _reset_threshold_inputs(self) -> None:
        """Reset threshold controls to default values."""
        for key, spinbox in self.threshold_inputs.items():
            spinbox.setValue(DEFAULT_THRESHOLDS[key])

    def _save_threshold_settings(self) -> None:
        """Save threshold values to QSettings."""
        saved_values: dict[str, float] = {}
        for key, spinbox in self.threshold_inputs.items():
            value = clamp_threshold(float(spinbox.value()))
            saved_values[key] = value
            self.settings.setValue(THRESHOLD_SETTING_KEYS[key], value)
        self.threshold_values = saved_values
        self._show_toast(self._tr("settings_saved_toast"))
        self._set_status(self._tr("settings_saved_status"))

    def _is_correlation_profile_rebuild_running(self) -> bool:
        thread = getattr(self, "correlation_rebuild_thread", None)
        return thread is not None and thread.isRunning()

    def _start_rebuild_correlation_profiles(self) -> None:
        if self._is_correlation_profile_rebuild_running():
            self._set_status(self._tr("status_rebuild_correlation_profiles_running"))
            return
        if self.worker_thread is not None or self.clear_thread is not None:
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return
        if hasattr(self, "_is_character_bulk_build_running") and self._is_character_bulk_build_running():
            self._set_status(self._tr("status_character_bulk_running"))
            return
        if hasattr(self, "_is_character_delete_running") and self._is_character_delete_running():
            self._set_status(self._tr("status_character_delete_busy"))
            return

        self.rebuild_correlation_profiles_button.setEnabled(False)
        self._set_status(self._tr("status_rebuild_correlation_profiles_start"))

        self.correlation_rebuild_thread = QThread(self)
        self.correlation_rebuild_worker = CorrelationProfileRebuildWorker(
            repo_root=self.repo_root,
            preferred_language=self.current_language,
        )
        self.correlation_rebuild_worker.moveToThread(self.correlation_rebuild_thread)

        self.correlation_rebuild_thread.started.connect(self.correlation_rebuild_worker.run)
        self.correlation_rebuild_worker.finished.connect(self._on_rebuild_correlation_profiles_finished)
        self.correlation_rebuild_worker.finished.connect(self.correlation_rebuild_thread.quit)
        self.correlation_rebuild_worker.finished.connect(self.correlation_rebuild_worker.deleteLater)
        self.correlation_rebuild_thread.finished.connect(self.correlation_rebuild_thread.deleteLater)
        self.correlation_rebuild_thread.finished.connect(self._on_rebuild_correlation_profiles_thread_finished)
        self.correlation_rebuild_thread.start()

    def _on_rebuild_correlation_profiles_finished(self, ok: bool, message: str, payload: object) -> None:
        if not ok:
            self._show_toast(self._tr("settings_rebuild_correlation_profiles_failed_toast"))
            self._set_status(
                self._tr(
                    "status_rebuild_correlation_profiles_failed",
                    error=message or self._tr("status_unknown_error"),
                ),
                is_error=True,
            )
            return

        result = payload if isinstance(payload, dict) else {}
        profile_count = int(result.get("profile_count", 0) or 0)
        self._show_toast(self._tr("settings_rebuild_correlation_profiles_done_toast"))
        if bool(result.get("empty_index", False)):
            self._set_status(self._tr("status_rebuild_correlation_profiles_empty"))
            return
        self._set_status(self._tr("status_rebuild_correlation_profiles_done", count=profile_count))

    def _on_rebuild_correlation_profiles_thread_finished(self) -> None:
        self.correlation_rebuild_thread = None
        self.correlation_rebuild_worker = None
        self.rebuild_correlation_profiles_button.setEnabled(True)

    def _show_toast(self, text: str) -> None:
        """Show temporary toast text."""
        self.toast_label.setText(text)
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(1800)

    def _hide_toast(self) -> None:
        """Hide toast label."""
        self.toast_label.hide()

    def _apply_language(self) -> None:
        """Refresh all user-facing static UI text."""
        self.analysis_menu_button.setText("")
        self.character_menu_button.setText("")
        self.settings_menu_button.setText("")
        self.analysis_menu_button.setToolTip(self._tr("menu_analysis"))
        self.character_menu_button.setToolTip(self._tr("menu_characters"))
        self.settings_menu_button.setToolTip(self._tr("menu_settings"))
        self._update_side_menu_icons()
        self.folder_button.setText(self._tr("btn_choose_folder"))
        self.images_button.setText(self._tr("btn_choose_images"))
        self.remove_all_button.setText(self._tr("btn_remove_all"))
        self.clear_tags_button.setText(self._tr("btn_clear_tags"))
        self.remove_tagged_button.setText(self._tr("btn_remove_tagged"))
        if self.worker_thread is None:
            self.start_button.setText(self._tr("btn_start_analysis"))
        else:
            self.start_button.setText(self._tr("btn_stop_analysis"))

        self.count_label.setText(self._tr("selected_count", count=self.image_model.rowCount()))
        if not self.image_paths_by_key:
            self.preview_label.set_placeholder(self._tr("preview_placeholder"))
            waiting_texts = {texts["status_waiting_select"] for texts in TRANSLATIONS.values()}
            if not self.status_label.text().strip() or self.status_label.text() in waiting_texts:
                self._set_status(self._tr("status_waiting_select"))

        self.character_page_title_label.setText(self._tr("character_page_title"))
        self.character_search_input.setPlaceholderText(self._tr("character_search_placeholder"))
        self.character_search_button.setText(self._tr("character_search_button"))
        self.character_library_search_input.setPlaceholderText(self._tr("character_library_search_placeholder"))
        self.character_library_search_button.setText(self._tr("character_library_search_button"))
        self.character_bulk_label.setText(self._tr("character_bulk_count_label"))
        self.character_bulk_button.setText(self._tr("character_bulk_build_button"))
        self.character_import_button.setText(self._tr("character_import_button"))
        self.character_add_refs_button.setText(self._tr("character_add_refs_button"))
        self.character_delete_button.setText(self._tr("character_delete_button"))
        self.character_refresh_button.setText(self._tr("character_refresh_button"))
        self.character_search_results_label.setText(self._tr("character_search_results_title"))
        self.character_library_label.setText(self._tr("character_library_title"))

        self.settings_title_label.setText(self._tr("settings_title"))
        self.settings_subtitle_label.setText(self._tr("settings_subtitle"))
        self.settings_range_hint_label.setText(
            self._tr("settings_range_hint", min=f"{THRESHOLD_MIN_VALUE:.2f}", max=f"{THRESHOLD_MAX_VALUE:.2f}")
        )
        self.settings_diff_hint_label.setText(self._tr("settings_diff_hint"))
        self.settings_threshold_note_label.setText(self._tr("settings_threshold_notes"))
        self.language_title_label.setText(self._tr("settings_language_title"))
        self.threshold_title_label.setText(self._tr("settings_threshold_title"))
        self.reset_settings_button.setText(self._tr("settings_reset"))
        self.save_settings_button.setText(self._tr("settings_save"))
        self.rebuild_correlation_profiles_button.setText(self._tr("settings_rebuild_correlation_profiles"))
        self.rebuild_correlation_profiles_hint_label.setText(self._tr("settings_rebuild_correlation_profiles_hint"))

        for key, label in self.threshold_name_labels.items():
            label.setText(self._tr(THRESHOLD_LABEL_KEYS[key]))
        range_hint = self._tr("settings_spin_hint", min=f"{THRESHOLD_MIN_VALUE:.2f}", max=f"{THRESHOLD_MAX_VALUE:.2f}")
        for label in self.threshold_range_labels.values():
            label.setText(range_hint)

        for code, _ in LANGUAGE_OPTIONS:
            button = self.language_buttons.get(code)
            if button is not None:
                button.setChecked(code == self.current_language)
        if hasattr(self, "_reload_character_library_list") and hasattr(self, "character_library_list"):
            self._reload_character_library_list()
        if hasattr(self, "_refresh_feature_text_language"):
            self._refresh_feature_text_language()

    def _apply_effects(self) -> None:
        """Apply drop shadow effects for modern floating look."""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(42)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(25, 35, 60, 70))
        self.window_frame.setGraphicsEffect(shadow)

    def _apply_style(self) -> None:
        """Apply QSS style."""
        spin_up_icon = str(SPIN_UP_ICON_PATH.resolve()).replace("\\", "/")
        spin_down_icon = str(SPIN_DOWN_ICON_PATH.resolve()).replace("\\", "/")
        self.setStyleSheet(build_window_qss(spin_up_icon, spin_down_icon))
