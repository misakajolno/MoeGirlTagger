"""Persistence helpers for custom character library management."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

try:
    from PIL import Image
except Exception:  # pragma: no cover - fallback when PIL is unavailable
    Image = None

SUPPORTED_LANGUAGE_CODES = ("zh-CN", "en-US", "ja-JP", "ko-KR")

SOURCE_DIR_SPLIT_TOKENS = (" - ", " – ", " — ", "|", "｜")
CANONICAL_SOURCE_DIR_ALIASES = {
    "blue_archive": (
        "blue_archive",
        "bluearchive",
        "蔚蓝档案",
        "ブルーアーカイブ",
        "블루아카이브",
    ),
    "genshin_impact": (
        "genshin_impact",
        "genshinimpact",
        "genshin",
        "yuanshen",
        "yuan_shen",
        "原神",
        "げんしん",
    ),
    "honkai_star_rail": (
        "honkai_star_rail",
        "honkai_starrail",
        "honkai_starrail",
        "hsr",
        "崩坏星穹铁道",
        "崩壊スターレイル",
        "崩壞星穹鐵道",
        "붕괴스타레일",
    ),
    "honkai_impact_3rd": (
        "honkai_impact_3rd",
        "honkai_impact3rd",
        "崩坏3",
        "崩壊3rd",
        "붕괴3rd",
    ),
    "zenless_zone_zero": (
        "zenless_zone_zero",
        "zenlesszonezero",
        "zzz",
        "绝区零",
        "ゼンレスゾーンゼロ",
        "젠레스존제로",
    ),
}


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def normalize_slug(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(char for char in lowered if char.isalnum() or char == "_").strip("_")


def _strip_source_title_suffix(value: str) -> str:
    title = str(value or "").strip()
    if not title:
        return ""
    earliest = len(title)
    found = False
    for token in SOURCE_DIR_SPLIT_TOKENS:
        index = title.find(token)
        if index <= 0:
            continue
        earliest = min(earliest, index)
        found = True
    if found:
        title = title[:earliest].strip()
    for token in ("（", "("):
        index = title.find(token)
        if index > 0:
            title = title[:index].strip()
    return title


def _canonical_source_dir_slug(source_title: str) -> str:
    stripped = _strip_source_title_suffix(source_title)
    slug = normalize_slug(stripped) or normalize_slug(str(source_title or "").strip())
    if not slug:
        return "unknown_source"

    for canonical, aliases in CANONICAL_SOURCE_DIR_ALIASES.items():
        normalized_aliases = {normalize_slug(alias) for alias in aliases if normalize_slug(alias)}
        normalized_aliases.add(canonical)
        for alias in normalized_aliases:
            if slug == alias or slug.startswith(f"{alias}_"):
                return canonical
    return slug


def canonical_source_key(source_title: str) -> str:
    """Return canonical source key for cross-language/source-title matching."""
    return _canonical_source_dir_slug(source_title)


def file_sha1(path: Path) -> str:
    hasher = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def image_phash(path: Path) -> int | None:
    if Image is None:
        return None
    try:
        with Image.open(path) as source:
            grayscale = source.convert("L").resize((8, 8))
            pixels = list(grayscale.getdata())
    except Exception:
        return None
    if not pixels:
        return None
    average = sum(pixels) / len(pixels)
    value = 0
    for pixel in pixels:
        value = (value << 1) | (1 if pixel >= average else 0)
    return value


def phash_distance(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def normalize_language_code(value: str, default: str = "zh-CN") -> str:
    candidate = str(value or "").strip()
    if candidate in SUPPORTED_LANGUAGE_CODES:
        return candidate
    lowered = candidate.lower()
    if lowered.startswith("zh"):
        return "zh-CN"
    if lowered.startswith("en"):
        return "en-US"
    if lowered.startswith("ja"):
        return "ja-JP"
    if lowered.startswith("ko"):
        return "ko-KR"
    return default if default in SUPPORTED_LANGUAGE_CODES else "zh-CN"


def infer_language_code(text: str) -> str:
    value = str(text or "")
    for char in value:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
            return "ko-KR"
        if 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF or 0xFF66 <= code <= 0xFF9D:
            return "ja-JP"
        if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            return "zh-CN"
    if any(char.isascii() and char.isalpha() for char in value):
        return "en-US"
    return "zh-CN"


def normalize_alias_entries(display_name: str, aliases: object) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def append_one(name_value: object, language_value: object = "") -> None:
        name = str(name_value or "").strip()
        if not name:
            return
        inferred = infer_language_code(name)
        language = normalize_language_code(str(language_value or "").strip(), default=inferred)
        key = (name.casefold(), language)
        if key in seen:
            return
        seen.add(key)
        result.append({"name": name, "language": language})

    append_one(display_name)
    items = aliases if isinstance(aliases, list) else []
    for item in items:
        if isinstance(item, dict):
            name = (
                item.get("name")
                or item.get("display_name")
                or item.get("value")
                or item.get("alias")
            )
            language = item.get("language") or item.get("lang")
            append_one(name, language)
            continue
        append_one(item)
    return result


def normalize_source_alias_entries(source_title: str, source_aliases: object) -> list[dict]:
    return normalize_alias_entries(source_title, source_aliases)


def normalize_provider_links(provider: str, provider_entity_id: str, provider_links: object) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def append_one(provider_value: object, entity_value: object) -> None:
        provider_text = str(provider_value or "").strip() or "manual"
        entity_text = str(entity_value or "").strip()
        if not entity_text:
            return
        key = (provider_text.casefold(), entity_text.casefold())
        if key in seen:
            return
        seen.add(key)
        result.append({"provider": provider_text, "provider_entity_id": entity_text})

    append_one(provider, provider_entity_id)
    items = provider_links if isinstance(provider_links, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        append_one(
            item.get("provider"),
            item.get("provider_entity_id") or item.get("entity_id") or item.get("id"),
        )
    return result


def _preferred_languages(language_code: str) -> list[str]:
    requested = normalize_language_code(language_code, default="zh-CN")
    preferred = [requested]
    for code in ("en-US", "ja-JP", "ko-KR", "zh-CN"):
        if code not in preferred:
            preferred.append(code)
    return preferred


def select_localized_entry(default_text: str, entries: object, language_code: str) -> str:
    normalized_default = str(default_text or "").strip()
    normalized_entries = normalize_alias_entries(normalized_default, entries)
    if not normalized_entries:
        return normalized_default

    for language in _preferred_languages(language_code):
        for entry in normalized_entries:
            if str(entry.get("language", "")).strip() != language:
                continue
            name = str(entry.get("name", "")).strip()
            if name:
                return name

    for entry in normalized_entries:
        name = str(entry.get("name", "")).strip()
        if name:
            return name
    return normalized_default


def select_localized_alias(record: dict, language_code: str) -> str:
    display_name = str(record.get("display_name", "")).strip()
    return select_localized_entry(display_name, record.get("aliases"), language_code)


def select_localized_source_title(record: dict, language_code: str) -> str:
    source_title = str(record.get("source_title", "")).strip()
    return select_localized_entry(source_title, record.get("source_aliases"), language_code)


class CustomCharacterStore:
    """Manage local custom character records and reference assets."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.characters_path = self.root / "characters.json"
        self.avatars_dir = self.root / "avatars"
        self.references_dir = self.root / "references"
        self.ensure_layout()

    def ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        self.references_dir.mkdir(parents=True, exist_ok=True)
        if not self.characters_path.exists():
            self._write_all([])
        self._migrate_reference_layout_by_source()

    def _reference_source_dir_name(self, source_title: str) -> str:
        return _canonical_source_dir_slug(source_title)

    def _reference_character_dir(self, record: dict) -> Path:
        source_dir = self._reference_source_dir_name(str(record.get("source_title", "")).strip())
        character_id = str(record.get("id", "")).strip()
        if not character_id:
            character_id = "unknown_character"
        return self.references_dir / source_dir / character_id

    def _is_inside_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root.resolve())
        except Exception:
            return False
        return True

    def _resolve_non_conflicting_target(self, source_path: Path, target_path: Path) -> Path:
        if not target_path.exists():
            return target_path
        try:
            if source_path.resolve() == target_path.resolve():
                return target_path
        except Exception:
            pass

        stem = target_path.stem
        suffix = target_path.suffix
        for index in range(1, 10000):
            candidate = target_path.with_name(f"{stem}_{index}{suffix}")
            if not candidate.exists():
                return candidate
        return target_path.with_name(f"{stem}_{now_iso().replace(':', '').replace('-', '')}{suffix}")

    def _prune_empty_reference_dirs(self) -> None:
        if not self.references_dir.exists():
            return
        directories = sorted(
            [path for path in self.references_dir.rglob("*") if path.is_dir()],
            key=lambda item: len(item.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                continue

    def _migrate_reference_layout_by_source(self) -> None:
        records = self._read_all()
        if not records:
            self._prune_empty_reference_dirs()
            return

        changed = False
        for index, record in enumerate(records):
            references = [str(value).replace("\\", "/").strip() for value in record.get("reference_images", [])]
            references = [value for value in references if value]
            if not references:
                continue
            character_dir = self._reference_character_dir(record)
            character_dir.mkdir(parents=True, exist_ok=True)

            migrated_references: list[str] = []
            seen: set[str] = set()
            for relative in references:
                source_path = (self.root / Path(relative)).resolve()
                if not self._is_inside_root(source_path):
                    continue
                if not source_path.exists() or not source_path.is_file():
                    continue
                target_path = character_dir / source_path.name
                if source_path != target_path:
                    target_path = self._resolve_non_conflicting_target(source_path, target_path)
                    if source_path != target_path:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(source_path), str(target_path))
                migrated_relative = target_path.relative_to(self.root).as_posix()
                if migrated_relative in seen:
                    continue
                seen.add(migrated_relative)
                migrated_references.append(migrated_relative)

            if migrated_references != references:
                updated = dict(record)
                updated["reference_images"] = migrated_references
                updated["updated_at"] = now_iso()
                records[index] = updated
                changed = True

        if changed:
            self._write_all(records)
        self._prune_empty_reference_dirs()

    def _read_all(self) -> list[dict]:
        if not self.characters_path.exists():
            return []
        try:
            payload = json.loads(self.characters_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        result: list[dict] = []
        for item in payload:
            if isinstance(item, dict):
                normalized = dict(item)
                display_name = str(normalized.get("display_name", "")).strip()
                normalized["display_name"] = display_name
                normalized["aliases"] = normalize_alias_entries(display_name, normalized.get("aliases"))
                source_title = str(normalized.get("source_title", "")).strip()
                normalized["source_title"] = source_title
                normalized["source_aliases"] = normalize_source_alias_entries(
                    source_title,
                    normalized.get("source_aliases"),
                )
                normalized_provider = str(normalized.get("provider", "")).strip() or "manual"
                normalized_entity_id = str(normalized.get("provider_entity_id", "")).strip()
                normalized["provider"] = normalized_provider
                normalized["provider_entity_id"] = normalized_entity_id
                normalized["provider_links"] = normalize_provider_links(
                    normalized_provider,
                    normalized_entity_id,
                    normalized.get("provider_links"),
                )
                result.append(normalized)
        return result

    def _write_all(self, records: list[dict]) -> None:
        self.characters_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.characters_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(self.characters_path)

    def list_characters(self) -> list[dict]:
        return self._read_all()

    def get_character(self, character_id: str) -> dict | None:
        target = str(character_id).strip()
        for record in self._read_all():
            if str(record.get("id", "")).strip() == target:
                return record
        return None

    def _ensure_character_id(self, display_name: str, source_title: str, provider: str, provider_entity_id: str) -> str:
        slug = normalize_slug(display_name) or "character"
        digest = hashlib.sha1(
            f"{display_name}|{source_title}|{provider}|{provider_entity_id}|{now_iso()}".encode("utf-8")
        ).hexdigest()[:8]
        return f"custom_{slug}_{digest}"

    def add_character(
        self,
        display_name: str,
        aliases: list[object] | None = None,
        source_title: str = "",
        source_aliases: list[object] | None = None,
        avatar_url: str = "",
        avatar_local_path: str = "",
        provider: str = "manual",
        provider_entity_id: str = "",
        enabled: bool = True,
    ) -> dict:
        records = self._read_all()
        normalized_provider = str(provider).strip() or "manual"
        normalized_entity_id = str(provider_entity_id).strip()
        if normalized_entity_id:
            for record in records:
                links = normalize_provider_links(
                    str(record.get("provider", "")).strip() or "manual",
                    str(record.get("provider_entity_id", "")).strip(),
                    record.get("provider_links"),
                )
                if any(
                    str(link.get("provider", "")).strip() == normalized_provider
                    and str(link.get("provider_entity_id", "")).strip() == normalized_entity_id
                    for link in links
                ):
                    return record

        created_at = now_iso()
        normalized_display_name = str(display_name).strip()
        record = {
            "id": self._ensure_character_id(normalized_display_name, source_title, normalized_provider, normalized_entity_id),
            "display_name": normalized_display_name,
            "aliases": normalize_alias_entries(normalized_display_name, aliases or []),
            "source_title": str(source_title).strip(),
            "source_aliases": normalize_source_alias_entries(str(source_title).strip(), source_aliases or []),
            "avatar_url": str(avatar_url).strip(),
            "avatar_local_path": str(avatar_local_path).replace("\\", "/").strip(),
            "provider": normalized_provider,
            "provider_entity_id": normalized_entity_id,
            "provider_links": normalize_provider_links(normalized_provider, normalized_entity_id, []),
            "reference_images": [],
            "enabled": bool(enabled),
            "created_at": created_at,
            "updated_at": created_at,
        }
        records.append(record)
        self._write_all(records)
        return record

    def update_character(self, character_id: str, **fields: object) -> dict:
        records = self._read_all()
        target = str(character_id).strip()
        for index, record in enumerate(records):
            if str(record.get("id", "")).strip() != target:
                continue
            updated = dict(record)
            for key, value in fields.items():
                if key == "id":
                    continue
                updated[key] = value
            normalized_display_name = str(updated.get("display_name", "")).strip()
            updated["display_name"] = normalized_display_name
            updated["aliases"] = normalize_alias_entries(normalized_display_name, updated.get("aliases"))
            normalized_source_title = str(updated.get("source_title", "")).strip()
            updated["source_title"] = normalized_source_title
            updated["source_aliases"] = normalize_source_alias_entries(
                normalized_source_title,
                updated.get("source_aliases"),
            )
            normalized_provider = str(updated.get("provider", "")).strip() or "manual"
            normalized_entity_id = str(updated.get("provider_entity_id", "")).strip()
            updated["provider"] = normalized_provider
            updated["provider_entity_id"] = normalized_entity_id
            updated["provider_links"] = normalize_provider_links(
                normalized_provider,
                normalized_entity_id,
                updated.get("provider_links"),
            )
            updated["updated_at"] = now_iso()
            records[index] = updated
            self._write_all(records)
            return updated
        raise KeyError(f"Character not found: {character_id}")

    def set_enabled(self, character_id: str, enabled: bool) -> dict:
        return self.update_character(character_id, enabled=bool(enabled))

    def append_reference_images(self, character_id: str, image_paths: list[Path]) -> dict:
        character = self.get_character(character_id)
        if character is None:
            raise KeyError(f"Character not found: {character_id}")

        character_dir = self._reference_character_dir(character)
        character_dir.mkdir(parents=True, exist_ok=True)
        existing: list[str] = []
        seen: set[str] = set()
        existing_phashes: list[int] = []
        for value in character.get("reference_images", []):
            relative = str(value).replace("\\", "/").strip()
            if not relative or relative in seen:
                continue
            resolved = (self.root / Path(relative)).resolve()
            if not resolved.exists() or not resolved.is_file():
                continue
            existing.append(relative)
            seen.add(relative)
            fingerprint = image_phash(resolved)
            if fingerprint is not None:
                existing_phashes.append(fingerprint)
        for source in image_paths:
            source_path = Path(source).resolve()
            if not source_path.exists() or not source_path.is_file():
                continue
            candidate_phash = image_phash(source_path)
            if candidate_phash is not None and any(
                phash_distance(candidate_phash, current) <= 2 for current in existing_phashes
            ):
                continue
            digest = file_sha1(source_path)[:16]
            suffix = source_path.suffix.lower() or ".img"
            target = character_dir / f"{digest}{suffix}"
            if not target.exists():
                shutil.copy2(source_path, target)
            relative = target.relative_to(self.root).as_posix()
            if relative not in seen:
                existing.append(relative)
                seen.add(relative)
                if candidate_phash is not None:
                    existing_phashes.append(candidate_phash)

        return self.update_character(character_id, reference_images=existing)

    def delete_character(self, character_id: str) -> bool:
        records = self._read_all()
        target = str(character_id).strip()
        kept: list[dict] = []
        removed_record: dict | None = None
        for record in records:
            if str(record.get("id", "")).strip() == target:
                removed_record = record
                continue
            kept.append(record)
        if removed_record is None:
            return False
        self._write_all(kept)

        references = [str(value).replace("\\", "/").strip() for value in removed_record.get("reference_images", [])]
        for relative in references:
            reference_path = (self.root / Path(relative)).resolve()
            if not self._is_inside_root(reference_path):
                continue
            if reference_path.exists() and reference_path.is_file():
                reference_path.unlink(missing_ok=True)

        legacy_dir = self.references_dir / target
        if legacy_dir.exists() and legacy_dir.is_dir():
            shutil.rmtree(legacy_dir, ignore_errors=True)
        for candidate_dir in self.references_dir.glob(f"*/{target}"):
            if candidate_dir.exists() and candidate_dir.is_dir():
                shutil.rmtree(candidate_dir, ignore_errors=True)
        self._prune_empty_reference_dirs()

        avatar_relative = str(removed_record.get("avatar_local_path", "")).strip()
        if avatar_relative:
            avatar_path = (self.root / avatar_relative).resolve()
            if avatar_path.exists() and avatar_path.is_file():
                avatar_path.unlink(missing_ok=True)
        return True

    def iter_reference_items(self, enabled_only: bool = True) -> list[tuple[dict, Path]]:
        result: list[tuple[dict, Path]] = []
        for record in self._read_all():
            if enabled_only and not bool(record.get("enabled", True)):
                continue
            references = [str(value).strip() for value in record.get("reference_images", []) if str(value).strip()]
            for relative in references:
                path = (self.root / Path(relative)).resolve()
                if path.exists() and path.is_file():
                    result.append((record, path))
        return result
