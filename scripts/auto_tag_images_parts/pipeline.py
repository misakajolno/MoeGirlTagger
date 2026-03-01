"""I/O and metadata pipeline helpers for auto tag image pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

try:
    from scripts.auto_tag_images_parts.constants import SUPPORTED_EXTENSIONS
    from scripts.auto_tag_images_parts.tagger import ensure_parent
    from scripts.write_tags_to_image_metadata import (
        build_target_records,
        ensure_exiftool,
        load_blocked_tags,
        load_display_priority,
        load_max_tags_per_category,
        load_taxonomy_map,
        load_taxonomy_structure,
        normalize_keywords,
        write_keywords_with_exiftool,
    )
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.auto_tag_images_parts.constants import SUPPORTED_EXTENSIONS
    from scripts.auto_tag_images_parts.tagger import ensure_parent
    from scripts.write_tags_to_image_metadata import (
        build_target_records,
        ensure_exiftool,
        load_blocked_tags,
        load_display_priority,
        load_max_tags_per_category,
        load_taxonomy_map,
        load_taxonomy_structure,
        normalize_keywords,
        write_keywords_with_exiftool,
    )

def collect_images(image_dir: Path, recursive: bool = True) -> list[Path]:
    """Collect image files under root.

    Args:
        image_dir: Image directory.
        recursive: Whether to scan recursively.

    Returns:
        Sorted image paths.
    """
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")

    pattern = "**/*" if recursive else "*"
    files = [
        path
        for path in image_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files, key=lambda item: item.as_posix())


def collect_images_from_list(list_path: Path, root_dir: Path) -> list[Path]:
    """Collect image files from a path list file.

    Args:
        list_path: Text file path with one image path per line.
        root_dir: Project root for resolving relative paths.

    Returns:
        Sorted distinct image paths.
    """
    if not list_path.exists():
        raise FileNotFoundError(f"Input list file not found: {list_path}")

    result: list[Path] = []
    seen: set[str] = set()
    for raw_line in list_path.read_text(encoding="utf-8").splitlines():
        text = raw_line.strip()
        if not text:
            continue
        path = Path(text)
        candidate = path if path.is_absolute() else (root_dir / path)
        resolved = candidate.resolve()
        normalized = resolved.as_posix().lower()
        if normalized in seen:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        seen.add(normalized)
        result.append(resolved)

    return sorted(result, key=lambda item: item.as_posix())


def file_sha1(path: Path) -> str:
    """Calculate file SHA1.

    Args:
        path: File path.

    Returns:
        SHA1 string.
    """
    hasher = hashlib.sha1()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_record(
    image_path: Path,
    root_path: Path,
    characters: list[str],
    feature_tags: list[str],
    source_game: list[str],
    now_iso: str,
) -> dict:
    """Build one annotation record.

    Args:
        image_path: Absolute image path.
        root_path: Project root.
        characters: Character names in Chinese.
        feature_tags: Canonical feature tags.
        source_game: Canonical game ids.
        now_iso: ISO timestamp.

    Returns:
        Annotation record.
    """
    try:
        normalized_image_path = image_path.relative_to(root_path).as_posix()
    except ValueError:
        normalized_image_path = image_path.as_posix()

    return {
        "image_id": file_sha1(image_path),
        "image_path": normalized_image_path,
        "characters": characters,
        "feature_tags": feature_tags,
        "source_game": source_game,
        "review_required": False,
        "status": "labeled_draft",
        "created_at": now_iso,
    }


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    """Write records to JSONL.

    Args:
        path: Output JSONL path.
        records: Record iterator.

    Returns:
        Written record count.
    """
    ensure_parent(path)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def process_and_write_metadata(
    queue_path: Path,
    image_root: Path,
    taxonomy_path: Path,
    priority_rules_path: Path,
    exiftool_dir: Path,
    sensitive_terms_path: Path | None = None,
    metadata_language: str = "zh-CN",
) -> tuple[int, int, int]:
    """Write queue records into image metadata.

    Args:
        queue_path: JSONL queue path.
        image_root: Image root.
        taxonomy_path: Taxonomy path.
        priority_rules_path: Priority rules path.
        exiftool_dir: Exiftool directory.
        metadata_language: Preferred metadata language code.

    Returns:
        Tuple of (target_count, updated_count, skipped_count).
    """
    records = [
        json.loads(line)
        for line in queue_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    target_records = build_target_records(records=records, status_filter={"labeled_draft"})
    language_code = str(metadata_language or "").strip() or "zh-CN"
    tag_to_zh = load_taxonomy_map(
        taxonomy_path,
        sensitive_terms_path=sensitive_terms_path,
        language_code=language_code,
    )
    tag_to_category, mutually_exclusive_groups = load_taxonomy_structure(
        taxonomy_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    max_tags_per_category = load_max_tags_per_category(
        priority_rules_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    blocked_tags = load_blocked_tags(
        priority_rules_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    category_rank, tag_rank = load_display_priority(
        priority_rules_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    exiftool_path = ensure_exiftool(exiftool_dir)

    updated = 0
    skipped = 0
    for record in target_records:
        image_abs_path = (image_root / Path(record["image_path"])).resolve()
        if not image_abs_path.exists():
            skipped += 1
            continue

        keywords = normalize_keywords(
            record=record,
            tag_to_zh=tag_to_zh,
            tag_to_category=tag_to_category,
            mutually_exclusive_groups=mutually_exclusive_groups,
            max_tags_per_category=max_tags_per_category,
            category_rank=category_rank,
            tag_rank=tag_rank,
            blocked_tags=blocked_tags,
        )
        if not keywords:
            skipped += 1
            continue

        write_keywords_with_exiftool(
            exiftool_path=exiftool_path,
            image_path=image_abs_path,
            keywords=keywords,
        )
        updated += 1

    return len(target_records), updated, skipped
