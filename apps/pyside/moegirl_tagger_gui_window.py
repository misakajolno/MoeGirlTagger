"""Main MoeGirlTagger window implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSettings, QThread, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QMainWindow, QPushButton

from apps.pyside.moegirl_character_manager_service import CharacterManagerService
from apps.pyside.moegirl_tagger_gui_common import (
    DEFAULT_LANGUAGE,
    DEFAULT_THRESHOLDS,
    LANGUAGE_SETTING_KEY,
    LAST_OPEN_DIR_SETTING_KEY,
    THRESHOLD_SETTING_KEYS,
    TRANSLATIONS,
    clamp_threshold,
    load_taxonomy_name_map,
    normalize_language_code,
)
from apps.pyside.moegirl_tagger_gui_model import ImageListModel
from apps.pyside.moegirl_tagger_gui_worker import AnalysisWorker
from apps.pyside.moegirl_tagger_gui_window_analysis_mixin import MoeGirlTaggerWindowAnalysisMixin
from apps.pyside.moegirl_tagger_gui_window_character_mixin import MoeGirlTaggerWindowCharacterMixin
from apps.pyside.moegirl_tagger_gui_window_ui_mixin import MoeGirlTaggerWindowUiMixin
from apps.pyside.moegirl_tagger_gui_workers import (
    CharacterBulkBuildWorker,
    CharacterDeleteWorker,
    CharacterLibrarySearchWorker,
    CharacterSearchWorker,
    CorrelationProfileRebuildWorker,
    ClearTagsWorker,
)
from core.moegirl_tagger.character_search_provider import SearchCandidate


class MoeGirlTaggerWindow(
    MoeGirlTaggerWindowUiMixin,
    MoeGirlTaggerWindowCharacterMixin,
    MoeGirlTaggerWindowAnalysisMixin,
    QMainWindow,
):
    """Main window for image selection and auto-tagging."""

    def __init__(self) -> None:
        """Initialize main window."""
        super().__init__()
        self.repo_root = Path(__file__).resolve().parents[2]
        self.image_root = (self.repo_root / "image").resolve()
        self.settings = QSettings("MoeGirlTabProject", "MoeGirlTagger")
        self.queue_output = (self.repo_root / "data/annotation_queue/pending_annotations_pyside.jsonl").resolve()
        self.current_language = normalize_language_code(str(self.settings.value(LANGUAGE_SETTING_KEY, DEFAULT_LANGUAGE)))
        self.taxonomy_name_map = load_taxonomy_name_map(
            (self.repo_root / "data/character_library/feature_taxonomy.json").resolve(),
            language_code=self.current_language,
        )
        side_menu_icon_dir = Path(__file__).resolve().parent / "assets" / "icons"
        self.analysis_menu_default_icon = self._load_side_menu_icon(side_menu_icon_dir / "sparkles_def.svg")
        self.analysis_menu_selected_icon = self._load_side_menu_icon(side_menu_icon_dir / "sparkles_high.svg")
        self.character_menu_default_icon = self._load_side_menu_icon(side_menu_icon_dir / "role_def.svg")
        self.character_menu_selected_icon = self._load_side_menu_icon(side_menu_icon_dir / "role_high.svg")
        self.settings_menu_default_icon = self._load_side_menu_icon(side_menu_icon_dir / "settings_def.svg")
        self.settings_menu_selected_icon = self._load_side_menu_icon(side_menu_icon_dir / "settings_high.svg")
        self.character_manager_service = CharacterManagerService(self.repo_root)
        self._setup_character_search_logger()
        self._recovered_stale_bulk_build = self.character_manager_service.mark_stale_bulk_build_if_needed()

        self.threshold_values = self._load_threshold_values()
        self.image_paths_by_key: dict[str, Path] = {}
        self.image_model = ImageListModel(self)
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None
        self.clear_thread: QThread | None = None
        self.clear_worker: ClearTagsWorker | None = None
        self.character_search_thread: QThread | None = None
        self.character_search_worker: CharacterSearchWorker | None = None
        self.character_library_search_thread: QThread | None = None
        self.character_library_search_worker: CharacterLibrarySearchWorker | None = None
        self.character_bulk_thread: QThread | None = None
        self.character_bulk_worker: CharacterBulkBuildWorker | None = None
        self.character_delete_thread: QThread | None = None
        self.character_delete_worker: CharacterDeleteWorker | None = None
        self.correlation_rebuild_thread: QThread | None = None
        self.correlation_rebuild_worker: CorrelationProfileRebuildWorker | None = None
        self.character_delete_preferred_row: int | None = None
        self.threshold_inputs: dict[str, QDoubleSpinBox] = {}
        self.threshold_name_labels: dict[str, QLabel] = {}
        self.threshold_range_labels: dict[str, QLabel] = {}
        self.language_buttons: dict[str, QPushButton] = {}
        self.search_candidates: list[SearchCandidate] = []
        self.search_candidate_avatar_payloads: dict[int, bytes] = {}
        self.character_library_filter_ids: set[str] | None = None
        self.character_icon_cache: dict[str, QIcon] = {}
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self._hide_toast)

        self._init_window()
        self._init_ui()
        self._apply_style()
        self._apply_effects()
        self._apply_language()
        self._sync_threshold_inputs()
        if self._recovered_stale_bulk_build:
            self._set_status(self._tr("status_character_bulk_recovered"), is_error=True)

    def _refresh_taxonomy_name_map(self) -> None:
        """Reload tag display names according to current UI language."""
        self.taxonomy_name_map = load_taxonomy_name_map(
            (self.repo_root / "data/character_library/feature_taxonomy.json").resolve(),
            language_code=self.current_language,
        )

    def _get_dialog_start_dir(self) -> Path:
        """Get preferred starting directory for file dialogs.

        Returns:
            Existing directory path.
        """
        raw = str(self.settings.value(LAST_OPEN_DIR_SETTING_KEY, "") or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()

        if self.image_root.exists() and self.image_root.is_dir():
            return self.image_root
        return self.repo_root

    def _remember_dialog_dir(self, folder: Path) -> None:
        """Persist last-used dialog directory.

        Args:
            folder: Selected folder.
        """
        try:
            resolved = folder.expanduser().resolve()
        except Exception:
            resolved = folder
        if resolved.exists() and resolved.is_dir():
            self.settings.setValue(LAST_OPEN_DIR_SETTING_KEY, str(resolved))

    def _load_threshold_values(self) -> dict[str, float]:
        """Load threshold values from persistent settings."""
        values: dict[str, float] = {}
        for key, default_value in DEFAULT_THRESHOLDS.items():
            setting_key = THRESHOLD_SETTING_KEYS[key]
            raw_value = self.settings.value(setting_key, default_value)
            try:
                parsed = float(raw_value)
            except (TypeError, ValueError):
                parsed = float(default_value)
            values[key] = clamp_threshold(parsed)
        return values

    def _tr(self, key: str, **kwargs) -> str:
        """Translate UI text with current language fallback."""
        language_dict = TRANSLATIONS.get(self.current_language, TRANSLATIONS[DEFAULT_LANGUAGE])
        template = language_dict.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _init_window(self) -> None:
        """Setup frameless window attributes."""
        self.setWindowTitle("MoeGirlTagger")
        self.setMinimumSize(1600, 980)
        self.resize(1880, 1080)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def _load_side_menu_icon(self, icon_path: Path) -> QIcon:
        """Load side menu icon file and return empty icon when missing."""
        if not icon_path.exists():
            return QIcon()
        return QIcon(str(icon_path))

    def _setup_character_search_logger(self) -> None:
        """Configure file logger for character search diagnostics."""
        logger = logging.getLogger("moegirl.character_search")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        log_dir = (self.repo_root / "data/logs").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = (log_dir / "character_search.log").resolve()

        for handler in logger.handlers:
            base_name = getattr(handler, "baseFilename", "")
            if base_name and Path(str(base_name)).resolve() == log_path:
                return

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
