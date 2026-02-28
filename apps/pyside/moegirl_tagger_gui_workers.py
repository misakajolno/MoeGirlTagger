"""Background worker objects used by MoeGirlTagger window."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from urllib.parse import urlparse, urlunparse

import requests
from PySide6.QtCore import QObject, Signal

from apps.pyside.moegirl_character_manager_service import CharacterManagerService
from apps.pyside.moegirl_tagger_gui_common import normalize_path_key
from core.moegirl_tagger.character_search_provider import SearchCandidate

AVATAR_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _build_avatar_fetch_urls(url: str) -> list[str]:
    normalized = str(url).strip()
    if not normalized:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def append(candidate: str) -> None:
        value = str(candidate).strip()
        if not value or value in seen:
            return
        seen.add(value)
        variants.append(value)

    append(normalized)
    parsed = urlparse(normalized)
    host = str(parsed.netloc or "").strip().lower()
    if host.endswith("wikia.nocookie.net"):
        path = str(parsed.path or "")
        scaled_path = re.sub(r"/revision/latest/scale-to-width-down/\d+", "/revision/latest", path, count=1)
        if scaled_path != path:
            append(urlunparse(parsed._replace(path=scaled_path)))
        revision_index = path.find("/revision/latest")
        if revision_index >= 0:
            original_path = path[:revision_index]
            append(urlunparse(parsed._replace(path=original_path)))
            append(urlunparse(parsed._replace(path=original_path, query="")))

    if parsed.query:
        append(urlunparse(parsed._replace(query="")))
    return variants


def _download_avatar_payload(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=(5, 10))
    response.raise_for_status()
    payload = bytes(response.content)
    if not payload:
        raise RuntimeError("empty avatar payload")
    content_type = str(response.headers.get("Content-Type", "")).strip().lower()
    if content_type and "image" not in content_type:
        raise RuntimeError(f"non-image avatar payload: {content_type}")
    return payload


def _prefetch_avatars(
    candidates: list[SearchCandidate],
    *,
    logger: logging.Logger,
    context: str,
) -> dict[int, bytes]:
    avatars: dict[int, bytes] = {}
    payload_cache: dict[str, bytes] = {}
    failed_urls: set[str] = set()
    session = requests.Session()
    session.headers.update(AVATAR_REQUEST_HEADERS)
    for index, candidate in enumerate(candidates):
        url = str(candidate.avatar_url).strip()
        if not url:
            continue
        if url in payload_cache:
            avatars[index] = payload_cache[url]
            continue
        if url in failed_urls:
            continue

        last_error: Exception | None = None
        try:
            for fetch_url in _build_avatar_fetch_urls(url):
                try:
                    payload = _download_avatar_payload(session, fetch_url)
                except Exception as error:
                    last_error = error
                    continue
                payload_cache[url] = payload
                avatars[index] = payload
                break
            else:
                failed_urls.add(url)
                logger.info(
                    "avatar prefetch failed context=%s url=%s error=%s",
                    context,
                    url,
                    last_error if last_error is not None else "unknown",
                )
        except Exception as error:
            failed_urls.add(url)
            logger.info("avatar prefetch failed context=%s url=%s error=%s", context, url, error)
    session.close()
    return avatars


class ClearTagsWorker(QObject):
    """Run metadata tag clearing in background thread."""

    finished = Signal(bool, str, list)

    def __init__(self, clear_func, exiftool: Path, image_paths: list[Path]) -> None:
        super().__init__()
        self._clear_func = clear_func
        self._exiftool = exiftool
        self._image_paths = list(image_paths)

    def run(self) -> None:
        try:
            self._clear_func(self._exiftool, self._image_paths)
        except RuntimeError as error:
            self.finished.emit(False, str(error), [])
            return
        except Exception as error:
            self.finished.emit(False, str(error), [])
            return
        self.finished.emit(True, "", [normalize_path_key(path) for path in self._image_paths])


class CharacterSearchWorker(QObject):
    """Run online character search and avatar prefetch in background thread."""

    finished = Signal(bool, str, object, object)

    def __init__(self, service: CharacterManagerService, keyword: str, limit: int = 50) -> None:
        super().__init__()
        self._service = service
        self._keyword = keyword
        self._limit = max(1, int(limit))
        self._logger = logging.getLogger("moegirl.character_search")

    def run(self) -> None:
        try:
            candidates = self._service.search_candidates(self._keyword, limit=self._limit)
            avatars = _prefetch_avatars(candidates, logger=self._logger, context=f"character:{self._keyword}")
            self.finished.emit(True, "", candidates, avatars)
        except Exception as error:
            self.finished.emit(False, str(error), [], {})


class CharacterBulkBuildWorker(QObject):
    """Run bulk character import in background thread."""

    progress = Signal(object)
    finished = Signal(bool, str, object)

    def __init__(self, service: CharacterManagerService, limit: int) -> None:
        super().__init__()
        self._service = service
        self._limit = max(1, int(limit))
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def _on_progress(self, payload: dict) -> None:
        self.progress.emit(payload)

    def _should_stop(self) -> bool:
        return self._stop_requested

    def run(self) -> None:
        try:
            summary = self._service.bulk_append_references_for_existing_characters(
                per_character_limit=self._limit,
                progress_callback=self._on_progress,
                stop_check=self._should_stop,
            )
            if str(summary.get("error", "")).strip():
                self.finished.emit(False, str(summary.get("error", "")).strip(), summary)
                return
            self.finished.emit(True, "", summary)
        except Exception as error:
            self.finished.emit(False, str(error), {})


class CharacterDeleteWorker(QObject):
    """Run character delete in background thread."""

    progress = Signal(object)
    finished = Signal(bool, str, object)

    def __init__(self, service: CharacterManagerService, character_ids: list[str]) -> None:
        super().__init__()
        self._service = service
        self._character_ids = [str(value).strip() for value in character_ids if str(value).strip()]
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        summary = {
            "total": len(self._character_ids),
            "processed": 0,
            "deleted": 0,
            "missing": 0,
            "failed": 0,
            "interrupted": False,
        }
        try:
            for index, character_id in enumerate(self._character_ids, start=1):
                if self._stop_requested:
                    summary["interrupted"] = True
                    break
                name = character_id
                record = self._service.get_character(character_id)
                if isinstance(record, dict):
                    raw_name = str(record.get("display_name", "")).strip()
                    if raw_name:
                        name = raw_name
                try:
                    removed = self._service.delete_character(character_id)
                    if removed:
                        summary["deleted"] += 1
                    else:
                        summary["missing"] += 1
                except Exception:
                    summary["failed"] += 1
                summary["processed"] = index
                self.progress.emit(dict(summary, current_name=name))
            self.finished.emit(True, "", summary)
        except Exception as error:
            self.finished.emit(False, str(error), summary)
