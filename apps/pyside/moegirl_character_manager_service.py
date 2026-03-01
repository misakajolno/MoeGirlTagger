"""Service layer for GUI character library management."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

import requests

from core.moegirl_tagger.character_search_provider import CharacterSearchProvider, SearchCandidate
from core.moegirl_tagger.custom_character_store import CustomCharacterStore, canonical_source_key
from core.moegirl_tagger.reference_identity_filter import ReferenceIdentityFilter


def download_avatar_file(url: str, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    with requests.get(url, stream=True, timeout=20, headers=headers) as response:
        response.raise_for_status()
        with target_path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    output.write(chunk)


class CharacterManagerService:
    """Facade for online search and local custom-character management."""

    def __init__(
        self,
        repo_root: Path,
        provider: CharacterSearchProvider | None = None,
        avatar_downloader=download_avatar_file,
        reference_identity_filter: ReferenceIdentityFilter | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.custom_root = (self.repo_root / "data/character_library/custom").resolve()
        self.store = CustomCharacterStore(self.custom_root)
        self.provider = provider if provider is not None else CharacterSearchProvider()
        self.avatar_downloader = avatar_downloader
        self.reference_identity_filter = (
            reference_identity_filter
            if reference_identity_filter is not None
            else ReferenceIdentityFilter(model_dir=(self.repo_root / "tools/clip-vit-b32").resolve())
        )
        self.logs_root = (self.repo_root / "data/logs").resolve()
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.build_state_path = (self.custom_root / "build_state.json").resolve()
        self.build_log_path = (self.logs_root / "character_build.log").resolve()

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.now().replace(microsecond=0).isoformat()

    def _write_build_log(self, level: str, message: str, *args: object) -> None:
        text = message
        if args:
            try:
                text = message % args
            except Exception:
                text = f"{message} | args={args!r}"
        self.build_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.build_log_path.open("a", encoding="utf-8") as output:
            output.write(f"{self._now_iso()} [{level}] {text}\n")

    def _load_build_state(self) -> dict:
        if not self.build_state_path.exists():
            return {}
        try:
            payload = json.loads(self.build_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _save_build_state(self, state: dict) -> None:
        self.build_state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.build_state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self.build_state_path)

    def is_first_bulk_build(self) -> bool:
        state = self._load_build_state()
        return not bool(state.get("has_completed_build", False))

    def mark_stale_bulk_build_if_needed(self) -> bool:
        state = self._load_build_state()
        if str(state.get("last_status", "")).strip() != "running":
            return False
        state["last_status"] = "interrupted"
        state["interrupted_at"] = self._now_iso()
        self._save_build_state(state)
        self._write_build_log("WARNING", "found stale running build state -> marked interrupted")
        return True

    def _find_existing_by_provider(self, provider: str, provider_entity_id: str) -> dict | None:
        key = self._candidate_provider_key(provider, provider_entity_id)
        if not key:
            return None
        for record in self.store.list_characters():
            if key in self._record_provider_entity_keys(record):
                return record
        return None

    @staticmethod
    def _candidate_provider_key(provider: str, provider_entity_id: str) -> str:
        normalized_provider = str(provider).strip().lower()
        normalized_id = str(provider_entity_id).strip().lower()
        if not normalized_provider or not normalized_id:
            return ""
        return f"{normalized_provider}:{normalized_id}"

    def _existing_provider_entity_keys(self) -> set[str]:
        keys: set[str] = set()
        for record in self.store.list_characters():
            keys.update(self._record_provider_entity_keys(record))
        return keys

    def _record_provider_entity_keys(self, record: dict) -> set[str]:
        keys: set[str] = set()
        primary_key = self._candidate_provider_key(
            str(record.get("provider", "")),
            str(record.get("provider_entity_id", "")),
        )
        if primary_key:
            keys.add(primary_key)
        links = record.get("provider_links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                link_key = self._candidate_provider_key(
                    str(link.get("provider", "")),
                    str(link.get("provider_entity_id", "")),
                )
                if link_key:
                    keys.add(link_key)
        return keys

    @staticmethod
    def _match_key(value: str) -> str:
        lowered = str(value or "").strip().lower()
        return "".join(char for char in lowered if char.isalnum())

    @staticmethod
    def _contains_non_ascii_letters(value: str) -> bool:
        for char in str(value or ""):
            if char.isalpha() and not char.isascii():
                return True
        return False

    def _match_overlap_length(self, first: str, second: str) -> int:
        left = str(first or "").strip()
        right = str(second or "").strip()
        if not left or not right:
            return 0
        if left in right:
            return len(left)
        if right in left:
            return len(right)
        return 0

    def _minimum_match_length(self, text: str) -> int:
        normalized = str(text or "").strip()
        if not normalized:
            return 0
        if self._contains_non_ascii_letters(normalized):
            return 2
        return 4

    def _build_source_keys(self, source_title: str) -> list[str]:
        text = str(source_title).strip()
        if not text:
            return []
        variants = [text]
        for separator in (" - ", " – ", " — ", "|", ":", "：", "（", "("):
            if separator in text:
                variants.append(text.split(separator, 1)[0])
        keys: list[str] = []
        seen: set[str] = set()
        for value in variants:
            key = self._match_key(value)
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
        return keys

    def _source_titles_compatible(self, left_source: str, right_source: str) -> bool:
        left_text = str(left_source).strip()
        right_text = str(right_source).strip()
        if not left_text or not right_text:
            return True
        left_canonical = canonical_source_key(left_text)
        right_canonical = canonical_source_key(right_text)
        if left_canonical and right_canonical and left_canonical == right_canonical:
            return True
        left_keys = self._build_source_keys(left_text)
        right_keys = self._build_source_keys(right_text)
        for left_key in left_keys:
            threshold = self._minimum_match_length(left_key)
            for right_key in right_keys:
                if self._match_overlap_length(left_key, right_key) >= max(2, threshold):
                    return True
        return False

    def _candidate_name_keys(self, candidate: SearchCandidate) -> set[str]:
        keys: set[str] = set()
        for raw in [candidate.display_name, candidate.source_title] + list(candidate.aliases):
            key = self._match_key(raw)
            if key:
                keys.add(key)
        return keys

    def _record_name_keys(self, record: dict) -> set[str]:
        keys: set[str] = set()
        display_name = str(record.get("display_name", "")).strip()
        display_key = self._match_key(display_name)
        if display_key:
            keys.add(display_key)
        aliases = record.get("aliases")
        if isinstance(aliases, list):
            for entry in aliases:
                if isinstance(entry, dict):
                    value = entry.get("name") or entry.get("display_name") or entry.get("value") or entry.get("alias")
                else:
                    value = entry
                alias_key = self._match_key(str(value or ""))
                if alias_key:
                    keys.add(alias_key)
        return keys

    @staticmethod
    def _provider_priority(provider: str) -> int:
        normalized = str(provider).strip().lower()
        if normalized == "anilist":
            return 4
        if normalized == "bangumi":
            return 3
        if normalized == "jikan":
            return 2
        if normalized == "manual":
            return 1
        return 0

    def _find_existing_by_identity(self, candidate: SearchCandidate) -> dict | None:
        candidate_keys = self._candidate_name_keys(candidate)
        if not candidate_keys:
            return None

        candidate_display_key = self._match_key(candidate.display_name)
        candidate_source = str(candidate.source_title).strip()
        for record in self.store.list_characters():
            record_keys = self._record_name_keys(record)
            if not record_keys:
                continue

            best_overlap = 0
            for candidate_key in candidate_keys:
                threshold = self._minimum_match_length(candidate_key)
                for record_key in record_keys:
                    overlap = self._match_overlap_length(candidate_key, record_key)
                    if overlap > best_overlap:
                        best_overlap = overlap
                    if overlap >= max(2, threshold):
                        if self._source_titles_compatible(candidate_source, str(record.get("source_title", ""))):
                            return record

            if candidate_display_key:
                display_overlap = max(
                    self._match_overlap_length(candidate_display_key, record_key)
                    for record_key in record_keys
                )
                # Fallback for cross-language sources: strong alias/name overlap can merge records.
                if display_overlap >= max(2, self._minimum_match_length(candidate_display_key) + 1):
                    return record

            _ = best_overlap
        return None

    def _merge_provider_links(self, record: dict, candidate: SearchCandidate) -> list[dict]:
        merged: list[dict] = []
        seen: set[str] = set()

        def append_link(provider_value: str, entity_value: str) -> None:
            link_key = self._candidate_provider_key(provider_value, entity_value)
            if not link_key or link_key in seen:
                return
            seen.add(link_key)
            provider_text = str(provider_value).strip()
            entity_text = str(entity_value).strip()
            if provider_text and entity_text:
                merged.append({"provider": provider_text, "provider_entity_id": entity_text})

        append_link(str(record.get("provider", "")), str(record.get("provider_entity_id", "")))
        links = record.get("provider_links")
        if isinstance(links, list):
            for link in links:
                if not isinstance(link, dict):
                    continue
                append_link(str(link.get("provider", "")), str(link.get("provider_entity_id", "")))
        append_link(candidate.provider, candidate.provider_entity_id)
        return merged

    def _merge_candidate_into_existing(self, record: dict, candidate: SearchCandidate) -> dict:
        merged_aliases: list[object] = []
        existing_aliases = record.get("aliases")
        if isinstance(existing_aliases, list):
            merged_aliases.extend(existing_aliases)
        merged_aliases.append(candidate.display_name)
        merged_aliases.extend(list(candidate.aliases))

        current_provider = str(record.get("provider", "")).strip()
        current_provider_entity_id = str(record.get("provider_entity_id", "")).strip()
        merged_provider = current_provider
        merged_provider_entity_id = current_provider_entity_id
        candidate_provider_key = self._candidate_provider_key(candidate.provider, candidate.provider_entity_id)
        if candidate_provider_key:
            if self._provider_priority(candidate.provider) >= self._provider_priority(current_provider):
                merged_provider = candidate.provider
                merged_provider_entity_id = candidate.provider_entity_id

        existing_source_title = str(record.get("source_title", "")).strip()
        candidate_source_title = str(candidate.source_title).strip()
        merged_source_title = existing_source_title or candidate_source_title
        if (
            existing_source_title
            and candidate_source_title
            and self._source_titles_compatible(existing_source_title, candidate_source_title)
            and len(candidate_source_title) > len(existing_source_title)
        ):
            merged_source_title = candidate_source_title

        merged_source_aliases: list[object] = []
        existing_source_aliases = record.get("source_aliases")
        if isinstance(existing_source_aliases, list):
            merged_source_aliases.extend(existing_source_aliases)
        if existing_source_title:
            merged_source_aliases.append(existing_source_title)
        if candidate_source_title:
            merged_source_aliases.append(candidate_source_title)

        merged_avatar_url = str(record.get("avatar_url", "")).strip() or str(candidate.avatar_url).strip()
        merged_provider_links = self._merge_provider_links(record, candidate)
        return self.store.update_character(
            str(record.get("id", "")).strip(),
            aliases=merged_aliases,
            source_title=merged_source_title,
            source_aliases=merged_source_aliases,
            avatar_url=merged_avatar_url,
            provider=merged_provider,
            provider_entity_id=merged_provider_entity_id,
            provider_links=merged_provider_links,
        )

    def _filter_existing_candidates(self, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        existing = self._existing_provider_entity_keys()
        if not existing:
            return list(candidates)
        filtered: list[SearchCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            provider_key = self._candidate_provider_key(candidate.provider, candidate.provider_entity_id)
            if provider_key and provider_key in existing:
                continue
            dedupe_key = provider_key or (
                f"{str(candidate.provider).strip().lower()}:"
                f"{str(candidate.display_name).strip().lower()}:"
                f"{str(candidate.source_title).strip().lower()}"
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            filtered.append(candidate)
        return filtered

    def search_candidates(self, keyword: str, limit: int = 20) -> list[SearchCandidate]:
        safe_limit = max(1, min(int(limit), 50))
        # Overfetch before filtering local-existing entries so repeated work-name
        # searches can still return new characters.
        provider_limit = max(120, safe_limit * 6)
        provider_limit = min(provider_limit, 300)
        candidates = self.provider.search(keyword, limit=provider_limit)
        filtered = self._filter_existing_candidates(candidates)
        return filtered[:safe_limit]

    def list_characters(self) -> list[dict]:
        return self.store.list_characters()

    def get_character(self, character_id: str) -> dict | None:
        return self.store.get_character(character_id)

    def import_candidate(
        self,
        candidate: SearchCandidate,
        *,
        avatar_payload: bytes | None = None,
        allow_avatar_download: bool = True,
        merge_strategy: Literal["auto", "merge", "new"] = "auto",
    ) -> dict:
        existing = self._find_existing_by_provider(candidate.provider, candidate.provider_entity_id)
        if existing is not None:
            return existing

        existing_identity = self._find_existing_by_identity(candidate)
        should_merge_identity = existing_identity is not None and merge_strategy != "new"
        if should_merge_identity:
            record = self._merge_candidate_into_existing(existing_identity, candidate)
        else:
            record = self.store.add_character(
                display_name=candidate.display_name,
                aliases=candidate.aliases,
                source_title=candidate.source_title,
                source_aliases=[candidate.source_title] if str(candidate.source_title).strip() else [],
                avatar_url=candidate.avatar_url,
                provider=candidate.provider,
                provider_entity_id=candidate.provider_entity_id,
                enabled=True,
            )

        avatar_relative = str(record.get("avatar_local_path", "")).strip()
        avatar_path: Path | None = None
        payload = bytes(avatar_payload) if avatar_payload else b""
        if payload:
            suffix = Path(urlparse(candidate.avatar_url).path).suffix.lower()
            if not suffix:
                suffix = ".jpg"
            avatar_path = self.store.avatars_dir / f"{record['id']}{suffix}"
            try:
                avatar_path.parent.mkdir(parents=True, exist_ok=True)
                avatar_path.write_bytes(payload)
                avatar_relative = avatar_path.relative_to(self.custom_root).as_posix()
                record = self.store.update_character(record["id"], avatar_local_path=avatar_relative)
            except Exception as error:
                self._write_build_log(
                    "WARNING",
                    "avatar payload save failed provider=%s entity=%s url=%s error=%s",
                    candidate.provider,
                    candidate.provider_entity_id,
                    candidate.avatar_url,
                    error,
                )
        if not avatar_relative and allow_avatar_download and candidate.avatar_url:
            suffix = Path(urlparse(candidate.avatar_url).path).suffix.lower()
            if not suffix:
                suffix = ".jpg"
            avatar_path = self.store.avatars_dir / f"{record['id']}{suffix}"
            try:
                self.avatar_downloader(candidate.avatar_url, avatar_path)
                avatar_relative = avatar_path.relative_to(self.custom_root).as_posix()
                record = self.store.update_character(record["id"], avatar_local_path=avatar_relative)
            except Exception as error:
                self._write_build_log(
                    "WARNING",
                    "avatar download failed provider=%s entity=%s url=%s error=%s",
                    candidate.provider,
                    candidate.provider_entity_id,
                    candidate.avatar_url,
                    error,
                )

        if avatar_relative:
            resolved_avatar = (self.custom_root / avatar_relative).resolve()
            if resolved_avatar.exists():
                record = self.store.append_reference_images(record["id"], [resolved_avatar])
        elif avatar_path and avatar_path.exists():
            record = self.store.append_reference_images(record["id"], [avatar_path])
        return record

    def preview_identity_merge_target(self, candidate: SearchCandidate) -> dict | None:
        if self._find_existing_by_provider(candidate.provider, candidate.provider_entity_id) is not None:
            return None
        return self._find_existing_by_identity(candidate)

    def delete_character(self, character_id: str) -> bool:
        return self.store.delete_character(character_id)

    def append_reference_images(self, character_id: str, image_paths: list[Path]) -> dict:
        return self.store.append_reference_images(character_id, image_paths)

    def set_enabled(self, character_id: str, enabled: bool) -> dict:
        return self.store.set_enabled(character_id, enabled=enabled)

    def _append_reference_urls(
        self,
        character_id: str,
        urls: list[str],
        *,
        identity_record: dict | None = None,
        identity_limit: int | None = None,
    ) -> int:
        record = self.store.get_character(character_id)
        if record is None:
            return 0
        before_count = len([value for value in record.get("reference_images", []) if str(value).strip()])
        if not urls:
            return 0

        local_paths: list[Path] = []
        with tempfile.TemporaryDirectory(prefix="character_refs_", dir=self.custom_root) as temp_dir:
            temp_root = Path(temp_dir)
            for index, raw_url in enumerate(urls):
                url = str(raw_url).strip()
                if not url:
                    continue
                suffix = Path(urlparse(url).path).suffix.lower()
                if not suffix:
                    suffix = ".jpg"
                target = temp_root / f"ref_{index}{suffix}"
                try:
                    self.avatar_downloader(url, target)
                    if target.exists() and target.is_file():
                        local_paths.append(target)
                except Exception as error:
                    self._write_build_log("WARNING", "reference download failed character=%s url=%s error=%s", character_id, url, error)

            if identity_record is not None and local_paths:
                safe_limit = max(1, min(int(identity_limit if identity_limit is not None else len(local_paths)), 30))
                try:
                    selected_paths, filter_report = self.reference_identity_filter.select_candidates(
                        record=dict(identity_record),
                        custom_root=self.custom_root,
                        candidate_paths=local_paths,
                        limit=safe_limit,
                    )
                    self._write_build_log(
                        "INFO",
                        (
                            "identity filter character=%s mode=%s candidates=%d scored=%d "
                            "kept=%d seeds=%d threshold=%.3f best=%.4f"
                        ),
                        character_id,
                        str(filter_report.get("mode", "")).strip(),
                        int(filter_report.get("candidate_count", 0) or 0),
                        int(filter_report.get("scored_count", 0) or 0),
                        int(filter_report.get("kept_count", len(selected_paths)) or 0),
                        int(filter_report.get("seed_count", 0) or 0),
                        float(filter_report.get("threshold", 0.0) or 0.0),
                        float(filter_report.get("best_similarity", 0.0) or 0.0),
                    )
                    local_paths = list(selected_paths)
                except Exception as error:
                    self._write_build_log("WARNING", "identity filter failed character=%s error=%s", character_id, error)
            if not local_paths:
                return 0
            updated = self.store.append_reference_images(character_id, local_paths)
            after_count = len([value for value in updated.get("reference_images", []) if str(value).strip()])
            return max(0, int(after_count) - int(before_count))

    def _prune_existing_references_by_identity(self, record: dict) -> int:
        character_id = str(record.get("id", "")).strip()
        if not character_id:
            return 0
        references = [str(value).strip() for value in record.get("reference_images", []) if str(value).strip()]
        if len(references) <= 1:
            return 0

        resolved_pairs: list[tuple[str, Path]] = []
        for relative in references:
            path = (self.custom_root / Path(relative)).resolve()
            if path.exists() and path.is_file():
                resolved_pairs.append((relative.replace("\\", "/"), path))
        if len(resolved_pairs) <= 1:
            return 0

        seed_record = dict(record)
        # Prune existing refs using avatar-only seed to avoid reinforcing prior contamination.
        seed_record["reference_images"] = []
        try:
            kept_paths, report = self.reference_identity_filter.select_candidates(
                record=seed_record,
                custom_root=self.custom_root,
                candidate_paths=[path for _, path in resolved_pairs],
                limit=len(resolved_pairs),
            )
        except Exception as error:
            self._write_build_log("WARNING", "identity prune failed character=%s error=%s", character_id, error)
            return 0

        kept_set = {Path(path).resolve().as_posix() for path in kept_paths}
        kept_relative: list[str] = []
        removed_paths: list[Path] = []
        for relative, path in resolved_pairs:
            if path.as_posix() in kept_set:
                kept_relative.append(relative)
            else:
                removed_paths.append(path)

        if kept_relative == [value for value, _ in resolved_pairs]:
            return 0

        updated = self.store.update_character(character_id, reference_images=kept_relative)
        for path in removed_paths:
            path.unlink(missing_ok=True)
        self._write_build_log(
            "INFO",
            (
                "identity prune character=%s mode=%s total=%d kept=%d removed=%d "
                "scored=%d seeds=%d best=%.4f"
            ),
            character_id,
            str(report.get("mode", "")).strip(),
            len(resolved_pairs),
            len(kept_relative),
            len(removed_paths),
            int(report.get("scored_count", 0) or 0),
            int(report.get("seed_count", 0) or 0),
            float(report.get("best_similarity", 0.0) or 0.0),
        )
        _ = updated
        return len(removed_paths)

    def bulk_append_references_for_existing_characters(
        self,
        per_character_limit: int = 5,
        progress_callback: Callable[[dict], None] | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> dict:
        safe_limit = max(1, min(int(per_character_limit), 30))
        records = self.store.list_characters()
        started_at = self._now_iso()
        summary = {
            "per_character_limit": safe_limit,
            "total_characters": len(records),
            "processed_characters": 0,
            "updated_characters": 0,
            "skipped_characters": 0,
            "failed_characters": 0,
            "added_references": 0,
            "pruned_references": 0,
            "interrupted": False,
            "error": "",
        }
        prior_state = self._load_build_state()
        self._save_build_state(
            {
                "last_status": "running",
                "started_at": started_at,
                "operation": "bulk_append_references",
                "target_limit": safe_limit,
                "has_completed_build": bool(prior_state.get("has_completed_build", False)),
            }
        )
        self._write_build_log(
            "INFO",
            "bulk reference append start total_characters=%d per_character_limit=%d",
            summary["total_characters"],
            safe_limit,
        )

        try:
            for index, record in enumerate(records, start=1):
                if stop_check is not None and stop_check():
                    summary["interrupted"] = True
                    break

                character_id = str(record.get("id", "")).strip()
                name = str(record.get("display_name", "")).strip()
                source_title = str(record.get("source_title", "")).strip()
                provider = str(record.get("provider", "")).strip()
                provider_entity_id = str(record.get("provider_entity_id", "")).strip()
                if not character_id or not name:
                    summary["skipped_characters"] += 1
                    summary["processed_characters"] = index
                    if progress_callback is not None:
                        progress_callback(dict(summary, current_name=name or "-"))
                    continue

                try:
                    pruned_count = self._prune_existing_references_by_identity(record)
                    if pruned_count > 0:
                        summary["pruned_references"] += int(pruned_count)
                        refreshed = self.store.get_character(character_id)
                        if isinstance(refreshed, dict):
                            record = refreshed
                    existing_references = [
                        value
                        for value in record.get("reference_images", [])
                        if str(value).strip()
                    ]
                    current_reference_count = len(existing_references)
                    remaining_limit = max(0, safe_limit - current_reference_count)
                    if remaining_limit <= 0:
                        summary["skipped_characters"] += 1
                        summary["processed_characters"] = index
                        if progress_callback is not None:
                            progress_callback(dict(summary, current_name=name))
                        continue
                    bulk_collector = getattr(self.provider, "collect_reference_image_urls_for_bulk", None)
                    if callable(bulk_collector):
                        urls = bulk_collector(
                            display_name=name,
                            source_title=source_title,
                            limit=remaining_limit,
                        )
                    else:
                        urls = self.provider.collect_reference_image_urls(
                            display_name=name,
                            source_title=source_title,
                            limit=remaining_limit,
                            provider=provider,
                            provider_entity_id=provider_entity_id,
                        )
                    added = self._append_reference_urls(
                        character_id,
                        urls,
                        identity_record=record,
                        identity_limit=remaining_limit,
                    )
                    if added > 0:
                        summary["updated_characters"] += 1
                        summary["added_references"] += int(added)
                    else:
                        summary["skipped_characters"] += 1
                except Exception as error:
                    summary["failed_characters"] += 1
                    self._write_build_log(
                        "WARNING",
                        "bulk reference append failed character=%s name=%s error=%s",
                        character_id,
                        name,
                        error,
                    )

                summary["processed_characters"] = index
                if progress_callback is not None:
                    progress_callback(dict(summary, current_name=name))
        except Exception as error:
            summary["error"] = str(error)
            self._write_build_log("ERROR", "bulk reference append failed: %s", error)

        finished_at = self._now_iso()
        has_completed = bool(prior_state.get("has_completed_build", False))
        if not summary["interrupted"] and not summary["error"] and summary["processed_characters"] > 0:
            has_completed = True

        if summary["error"]:
            last_status = "failed"
        elif summary["interrupted"]:
            last_status = "interrupted"
        else:
            last_status = "completed"

        final_state = {
            "last_status": last_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "operation": "bulk_append_references",
            "target_limit": safe_limit,
            "has_completed_build": has_completed,
            "summary": summary,
        }
        self._save_build_state(final_state)
        self._write_build_log(
            "INFO",
            (
                "bulk reference append done status=%s processed=%d total=%d "
                "updated=%d skipped=%d failed=%d added_references=%d interrupted=%s"
            ),
            last_status,
            summary["processed_characters"],
            summary["total_characters"],
            summary["updated_characters"],
            summary["skipped_characters"],
            summary["failed_characters"],
            summary["added_references"],
            summary["interrupted"],
        )
        return summary

    def bulk_import_popular_characters(
        self,
        limit: int = 1000,
        progress_callback: Callable[[dict], None] | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> dict:
        requested = max(1, min(int(limit), 5000))
        started_at = self._now_iso()
        summary = {
            "requested": requested,
            "fetched": 0,
            "processed": 0,
            "added": 0,
            "skipped": 0,
            "failed": 0,
            "interrupted": False,
            "error": "",
        }
        prior_state = self._load_build_state()
        self._save_build_state(
            {
                "last_status": "running",
                "started_at": started_at,
                "target_limit": requested,
                "has_completed_build": bool(prior_state.get("has_completed_build", False)),
            }
        )
        self._write_build_log("INFO", "bulk build start requested=%d", requested)

        try:
            candidates = self.provider.fetch_popular_characters(limit=requested)
            summary["fetched"] = len(candidates)
            existing_keys = self._existing_provider_entity_keys()

            for index, candidate in enumerate(candidates, start=1):
                if stop_check is not None and stop_check():
                    summary["interrupted"] = True
                    break

                key = f"{candidate.provider}:{candidate.provider_entity_id}".lower()
                if key in existing_keys and candidate.provider_entity_id:
                    summary["skipped"] += 1
                    summary["processed"] = index
                    if progress_callback is not None:
                        progress_callback(dict(summary, current_name=candidate.display_name))
                    continue

                try:
                    imported = self.import_candidate(candidate)
                    summary["added"] += 1
                    existing_keys.update(self._record_provider_entity_keys(imported))
                except Exception as error:
                    summary["failed"] += 1
                    self._write_build_log(
                        "WARNING",
                        "bulk import failed index=%d provider=%s entity=%s name=%s error=%s",
                        index,
                        candidate.provider,
                        candidate.provider_entity_id,
                        candidate.display_name,
                        error,
                    )
                summary["processed"] = index
                if progress_callback is not None:
                    progress_callback(dict(summary, current_name=candidate.display_name))
        except Exception as error:
            summary["error"] = str(error)
            self._write_build_log("ERROR", "bulk build failed: %s", error)

        finished_at = self._now_iso()
        has_completed = bool(prior_state.get("has_completed_build", False))
        if not summary["interrupted"] and not summary["error"] and summary["added"] > 0:
            has_completed = True

        if summary["error"]:
            last_status = "failed"
        elif summary["interrupted"]:
            last_status = "interrupted"
        else:
            last_status = "completed"

        final_state = {
            "last_status": last_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "target_limit": requested,
            "has_completed_build": has_completed,
            "summary": summary,
        }
        self._save_build_state(final_state)
        self._write_build_log(
            "INFO",
            "bulk build done status=%s requested=%d fetched=%d processed=%d added=%d skipped=%d failed=%d interrupted=%s",
            last_status,
            summary["requested"],
            summary["fetched"],
            summary["processed"],
            summary["added"],
            summary["skipped"],
            summary["failed"],
            summary["interrupted"],
        )
        return summary
