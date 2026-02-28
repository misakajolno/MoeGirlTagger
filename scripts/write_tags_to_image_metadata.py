"""Write localized tags into image metadata keywords fields."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

import requests

DEFAULT_QUEUE = Path("data/annotation_queue/pending_annotations.jsonl")
DEFAULT_TAXONOMY = Path("data/character_library/feature_taxonomy.json")
DEFAULT_PRIORITY_RULES = Path("data/character_library/feature_priority_rules.json")
DEFAULT_SENSITIVE_TERMS = Path("data/character_library/sensitive_terms.json")
DEFAULT_EXIFTOOL_DIR = Path("tools/exiftool")
DEFAULT_LANGUAGE = "zh-CN"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-tw": "zh-CN",
    "zh_tw": "zh-CN",
    "zh-hant": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
    "en_us": "en-US",
    "ja": "ja-JP",
    "ja-jp": "ja-JP",
    "ja_jp": "ja-JP",
    "ko": "ko-KR",
    "ko-kr": "ko-KR",
    "ko_kr": "ko-KR",
}


def normalize_language_code(value: str, default: str = DEFAULT_LANGUAGE) -> str:
    """Normalize language code to supported set."""
    text = str(value or "").strip()
    if not text:
        return default
    direct = LANGUAGE_ALIASES.get(text, "")
    if direct:
        return direct
    lowered = text.lower()
    return LANGUAGE_ALIASES.get(lowered, default)


def _language_candidates(language_code: str) -> tuple[str, ...]:
    normalized = normalize_language_code(language_code)
    mapping = {
        "zh-CN": ("zh-CN", "zh_CN", "zh-Hans", "zh", "zh-hans"),
        "en-US": ("en-US", "en_US", "en", "en-us"),
        "ja-JP": ("ja-JP", "ja_JP", "ja", "ja-jp"),
        "ko-KR": ("ko-KR", "ko_KR", "ko", "ko-kr"),
    }
    return mapping.get(normalized, (normalized,))


def _tag_name_field_candidates(language_code: str) -> tuple[str, ...]:
    normalized = normalize_language_code(language_code)
    if normalized == "zh-CN":
        return ("name_zh_cn", "name_zh")
    if normalized == "en-US":
        return ("name_en_us", "name_en")
    if normalized == "ja-JP":
        return ("name_ja_jp", "name_ja", "name_en")
    if normalized == "ko-KR":
        return ("name_ko_kr", "name_ko", "name_en")
    return ("name_en", "name_zh")


def _humanize_tag_id(tag_id: str) -> str:
    text = re.sub(r"[_\-\s]+", " ", str(tag_id or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else ""


def _resolve_localized_tag_name(tag: dict, language_code: str, tag_id: str) -> str:
    i18n_payload = tag.get("name_i18n", {})
    if isinstance(i18n_payload, dict):
        for candidate in _language_candidates(language_code):
            value = str(i18n_payload.get(candidate, "")).strip()
            if value:
                return value

    for field_name in _tag_name_field_candidates(language_code):
        value = str(tag.get(field_name, "")).strip()
        if value:
            return value

    zh_name = str(tag.get("name_zh", "")).strip()
    en_name = str(tag.get("name_en", "")).strip()
    normalized = normalize_language_code(language_code)
    if zh_name and normalized == "zh-CN":
        return zh_name
    if en_name:
        return en_name
    if zh_name:
        return zh_name if normalized == "zh-CN" else _humanize_tag_id(tag_id)
    return _humanize_tag_id(tag_id) or str(tag_id).strip()


def resolve_sensitive_terms_path(reference_path: Path, sensitive_terms_path: Path | None = None) -> Path:
    """Resolve sensitive terms path.

    Args:
        reference_path: Base file path used as anchor.
        sensitive_terms_path: Optional explicit sensitive terms file path.

    Returns:
        Resolved sensitive terms path.
    """
    if sensitive_terms_path is not None:
        return sensitive_terms_path
    return reference_path.parent / "sensitive_terms.json"


def load_sensitive_terms_payload(
    reference_path: Path,
    sensitive_terms_path: Path | None = None,
) -> dict:
    """Load optional sensitive terms extension payload.

    Args:
        reference_path: Base file path used as anchor.
        sensitive_terms_path: Optional explicit sensitive terms file path.

    Returns:
        Parsed payload. Empty dict when file missing/invalid shape.
    """
    path = resolve_sensitive_terms_path(reference_path, sensitive_terms_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _merge_tags(existing_tags: list, extra_tags: list) -> list:
    """Merge canonical tag list by tag id while preserving order."""
    merged = list(existing_tags)
    seen_ids: set[str] = set()
    for tag in merged:
        if isinstance(tag, dict):
            tag_id = str(tag.get("id", "")).strip()
            if tag_id:
                seen_ids.add(tag_id)
    for tag in extra_tags:
        if not isinstance(tag, dict):
            continue
        tag_id = str(tag.get("id", "")).strip()
        if not tag_id or tag_id in seen_ids:
            continue
        merged.append(tag)
        seen_ids.add(tag_id)
    return merged


def _merge_taxonomy_payload(base_taxonomy: dict, sensitive_payload: dict) -> dict:
    """Merge sensitive taxonomy extension into base taxonomy payload."""
    merged = dict(base_taxonomy)
    base_categories = list(merged.get("categories", []))
    category_index: dict[str, dict] = {}
    for category in base_categories:
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id", "")).strip()
        if category_id:
            category_index[category_id] = category

    extension = sensitive_payload.get("taxonomy", {})
    if not isinstance(extension, dict):
        merged["categories"] = base_categories
        return merged

    for category in extension.get("categories", []):
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id", "")).strip()
        if not category_id:
            continue
        existing = category_index.get(category_id)
        if existing is None:
            base_categories.append(category)
            category_index[category_id] = category
            continue
        existing_tags = existing.get("tags", [])
        extra_tags = category.get("tags", [])
        if isinstance(existing_tags, list) and isinstance(extra_tags, list):
            existing["tags"] = _merge_tags(existing_tags, extra_tags)

    base_groups = merged.get("mutually_exclusive_groups", {})
    if not isinstance(base_groups, dict):
        base_groups = {}
    extra_groups = extension.get("mutually_exclusive_groups", {})
    if isinstance(extra_groups, dict):
        for group_name, values in extra_groups.items():
            if not isinstance(values, list):
                continue
            key = str(group_name)
            existing_values = base_groups.get(key, [])
            if not isinstance(existing_values, list):
                existing_values = []
            merged_values: list[str] = []
            seen_values: set[str] = set()
            for item in [*existing_values, *values]:
                value = str(item).strip()
                if value and value not in seen_values:
                    merged_values.append(value)
                    seen_values.add(value)
            base_groups[key] = merged_values

    merged["categories"] = base_categories
    merged["mutually_exclusive_groups"] = base_groups
    return merged


def load_taxonomy_payload(
    taxonomy_path: Path,
    sensitive_terms_path: Path | None = None,
) -> dict:
    """Load merged taxonomy payload with optional sensitive-term extensions."""
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    sensitive_payload = load_sensitive_terms_payload(taxonomy_path, sensitive_terms_path)
    return _merge_taxonomy_payload(taxonomy, sensitive_payload)


def load_taxonomy_map(
    taxonomy_path: Path,
    sensitive_terms_path: Path | None = None,
    language_code: str = DEFAULT_LANGUAGE,
) -> dict[str, str]:
    """Load feature tag-id to localized display-name mapping.

    Args:
        taxonomy_path: Path to taxonomy JSON.
        language_code: Preferred output language code.

    Returns:
        Mapping from canonical tag to localized display name.
    """
    taxonomy = load_taxonomy_payload(taxonomy_path, sensitive_terms_path=sensitive_terms_path)
    normalized_language = normalize_language_code(language_code)
    mapping: dict[str, str] = {}
    for category in taxonomy["categories"]:
        for tag in category["tags"]:
            tag_id = str(tag.get("id", "")).strip()
            if not tag_id:
                continue
            mapping[tag_id] = _resolve_localized_tag_name(tag, normalized_language, tag_id)
    return mapping


def load_taxonomy_structure(
    taxonomy_path: Path,
    sensitive_terms_path: Path | None = None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Load taxonomy structures for precision filtering.

    Args:
        taxonomy_path: Taxonomy JSON path.

    Returns:
        Tuple of tag->category and mutually exclusive groups.
    """
    taxonomy = load_taxonomy_payload(taxonomy_path, sensitive_terms_path=sensitive_terms_path)
    tag_to_category: dict[str, str] = {}
    for category in taxonomy["categories"]:
        category_id = category["id"]
        for tag in category["tags"]:
            tag_to_category[tag["id"]] = category_id

    groups = taxonomy.get("mutually_exclusive_groups", {})
    mutually_exclusive_groups = {
        str(group_name): [str(tag) for tag in tags]
        for group_name, tags in groups.items()
    }
    return tag_to_category, mutually_exclusive_groups


def _merge_unique_str_list(base_values: object, extra_values: object) -> list[str]:
    """Merge two string lists while preserving order and uniqueness."""
    merged: list[str] = []
    seen: set[str] = set()
    for raw in [*(base_values if isinstance(base_values, list) else []), *(extra_values if isinstance(extra_values, list) else [])]:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if value and value not in seen:
            merged.append(value)
            seen.add(value)
    return merged


def _merge_post_rules(base_rules: object, extra_rules: object) -> list[dict]:
    """Merge post_rules list by rule id."""
    merged = list(base_rules if isinstance(base_rules, list) else [])
    seen_ids: set[str] = set()
    for rule in merged:
        if isinstance(rule, dict):
            rule_id = str(rule.get("id", "")).strip()
            if rule_id:
                seen_ids.add(rule_id)
    for rule in extra_rules if isinstance(extra_rules, list) else []:
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("id", "")).strip()
        if not rule_id or rule_id in seen_ids:
            continue
        merged.append(rule)
        seen_ids.add(rule_id)
    return merged


def load_priority_rules_payload(
    priority_rules_path: Path,
    sensitive_terms_path: Path | None = None,
) -> dict:
    """Load merged priority rules with optional sensitive extensions."""
    rules = json.loads(priority_rules_path.read_text(encoding="utf-8"))
    if not isinstance(rules, dict):
        return {}

    sensitive_payload = load_sensitive_terms_payload(priority_rules_path, sensitive_terms_path)
    extension = sensitive_payload.get("priority_rules", {})
    if not isinstance(extension, dict):
        return rules

    merged = dict(rules)
    merged["tag_priority_order"] = _merge_unique_str_list(
        merged.get("tag_priority_order", []),
        extension.get("tag_priority_order", []),
    )
    merged["display_tag_priority"] = _merge_unique_str_list(
        merged.get("display_tag_priority", []),
        extension.get("display_tag_priority", []),
    )
    merged["adult_display_layer_order"] = _merge_unique_str_list(
        merged.get("adult_display_layer_order", []),
        extension.get("adult_display_layer_order", []),
    )

    base_layers = merged.get("adult_display_layers", {})
    if not isinstance(base_layers, dict):
        base_layers = {}
    extra_layers = extension.get("adult_display_layers", {})
    if isinstance(extra_layers, dict):
        for layer_name, tags in extra_layers.items():
            key = str(layer_name).strip()
            if not key:
                continue
            base_layers[key] = _merge_unique_str_list(base_layers.get(key, []), tags)
    merged["adult_display_layers"] = base_layers

    base_conflict = merged.get("conflict_resolution", {})
    if not isinstance(base_conflict, dict):
        base_conflict = {}
    extra_conflict = extension.get("conflict_resolution", {})
    if isinstance(extra_conflict, dict):
        base_conflict["blocked_tags"] = _merge_unique_str_list(
            base_conflict.get("blocked_tags", []),
            extra_conflict.get("blocked_tags", []),
        )
        base_conflict["adult_hard_review_tags"] = _merge_unique_str_list(
            base_conflict.get("adult_hard_review_tags", []),
            extra_conflict.get("adult_hard_review_tags", []),
        )
        base_max = base_conflict.get("max_tags_per_category", {})
        if not isinstance(base_max, dict):
            base_max = {}
        extra_max = extra_conflict.get("max_tags_per_category", {})
        if isinstance(extra_max, dict):
            for category, value in extra_max.items():
                try:
                    base_max[str(category)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue
        base_conflict["max_tags_per_category"] = base_max
    merged["conflict_resolution"] = base_conflict

    merged["post_rules"] = _merge_post_rules(
        merged.get("post_rules", []),
        extension.get("post_rules", []),
    )
    return merged


def parse_jsonl(queue_path: Path) -> list[dict]:
    """Parse JSONL into record list.

    Args:
        queue_path: Input JSONL path.

    Returns:
        Parsed records.
    """
    records: list[dict] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            records.append(json.loads(text))
    return records


def load_max_tags_per_category(
    priority_rules_path: Path,
    sensitive_terms_path: Path | None = None,
) -> dict[str, int]:
    """Load per-category max tag counts.

    Args:
        priority_rules_path: Path to feature priority rules JSON.

    Returns:
        Category max-count mapping.
    """
    if not priority_rules_path.exists():
        return {}

    rules = load_priority_rules_payload(priority_rules_path, sensitive_terms_path=sensitive_terms_path)
    raw_mapping = (
        rules.get("conflict_resolution", {})
        .get("max_tags_per_category", {})
    )
    result: dict[str, int] = {}
    for category, value in raw_mapping.items():
        try:
            result[str(category)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return result


def load_blocked_tags(
    priority_rules_path: Path,
    sensitive_terms_path: Path | None = None,
) -> set[str]:
    """Load hard-blocked feature tags.

    Args:
        priority_rules_path: Path to feature priority rules JSON.

    Returns:
        Set of canonical tags that must never be output.
    """
    if not priority_rules_path.exists():
        return set()

    rules = load_priority_rules_payload(priority_rules_path, sensitive_terms_path=sensitive_terms_path)
    blocked = (
        rules.get("conflict_resolution", {})
        .get("blocked_tags", [])
    )
    result: set[str] = set()
    if isinstance(blocked, list):
        for tag in blocked:
            if isinstance(tag, str) and tag.strip():
                result.add(tag.strip())
    return result


def load_display_priority(
    priority_rules_path: Path,
    sensitive_terms_path: Path | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    """Load category and tag-level display priority.

    Args:
        priority_rules_path: Path to feature priority rules JSON.

    Returns:
        Tuple(category_rank_map, tag_rank_map), lower rank means earlier.
    """
    if not priority_rules_path.exists():
        return {}, {}

    rules = load_priority_rules_payload(priority_rules_path, sensitive_terms_path=sensitive_terms_path)
    category_order = list(rules.get("tag_priority_order", []))
    base_tag_order = list(rules.get("display_tag_priority", []))
    adult_layer_order = list(rules.get("adult_display_layer_order", []))
    adult_layers = rules.get("adult_display_layers", {})

    tag_order: list[str] = []
    seen: set[str] = set()

    for tag in base_tag_order:
        if isinstance(tag, str) and tag and tag not in seen:
            seen.add(tag)
            tag_order.append(tag)

    if isinstance(adult_layers, dict):
        for layer_name in adult_layer_order:
            layer_tags = adult_layers.get(layer_name, [])
            if not isinstance(layer_tags, list):
                continue
            for tag in layer_tags:
                if isinstance(tag, str) and tag and tag not in seen:
                    seen.add(tag)
                    tag_order.append(tag)

    category_rank = {name: index for index, name in enumerate(category_order)}
    tag_rank = {name: index for index, name in enumerate(tag_order)}
    return category_rank, tag_rank


def apply_precision_filter(
    feature_tags: list[str],
    tag_to_category: dict[str, str],
    mutually_exclusive_groups: dict[str, list[str]],
    max_tags_per_category: dict[str, int],
    blocked_tags: set[str] | None = None,
) -> list[str]:
    """Apply strict automatic precision controls to feature tags.

    Args:
        feature_tags: Raw feature tags from record.
        tag_to_category: Canonical tag->category mapping.
        mutually_exclusive_groups: Mutually exclusive tag groups.
        max_tags_per_category: Category max-count constraints.
        blocked_tags: Hard-blocked canonical tags.

    Returns:
        Filtered canonical tags.
    """
    seen: set[str] = set()
    ordered = []
    blocked = blocked_tags if blocked_tags else set()
    for tag in feature_tags:
        if tag in blocked:
            continue
        if tag not in tag_to_category:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        ordered.append(tag)

    removed: set[str] = set()
    for group_tags in mutually_exclusive_groups.values():
        present = [tag for tag in ordered if tag in group_tags and tag not in removed]
        if len(present) <= 1:
            continue
        for tag in present[1:]:
            removed.add(tag)

    category_counts: dict[str, int] = {}
    result: list[str] = []
    for tag in ordered:
        if tag in removed:
            continue
        category = tag_to_category.get(tag)
        if category is None:
            continue
        limit = max_tags_per_category.get(category, 999)
        current = category_counts.get(category, 0)
        if current >= limit:
            continue
        result.append(tag)
        category_counts[category] = current + 1
    return result


def sort_feature_tags_for_display(
    feature_tags: list[str],
    tag_to_category: dict[str, str],
    category_rank: dict[str, int],
    tag_rank: dict[str, int],
) -> list[str]:
    """Sort feature tags for metadata display readability.

    Args:
        feature_tags: Filtered canonical tags.
        tag_to_category: Canonical tag -> category mapping.
        category_rank: Category order mapping.
        tag_rank: Fine-grained tag order mapping.

    Returns:
        Ordered feature tags.
    """
    indexed = list(enumerate(feature_tags))

    def key(item: tuple[int, str]) -> tuple[int, int, int]:
        original_index, tag = item
        category = tag_to_category.get(tag, "")
        category_order = category_rank.get(category, 999)
        tag_order = tag_rank.get(tag, 999)
        return category_order, tag_order, original_index

    return [tag for _, tag in sorted(indexed, key=key)]


def normalize_keywords(
    record: dict,
    tag_to_zh: dict[str, str],
    tag_to_category: dict[str, str],
    mutually_exclusive_groups: dict[str, list[str]],
    max_tags_per_category: dict[str, int],
    category_rank: dict[str, int],
    tag_rank: dict[str, int],
    blocked_tags: set[str] | None = None,
) -> list[str]:
    """Build ordered localized keywords for one record.

    Args:
        record: Annotation record.
        tag_to_zh: Canonical tag -> localized feature name.

    Returns:
        Distinct keyword list.
    """
    keywords: list[str] = []

    for character in record.get("characters", []):
        if character and character not in keywords:
            keywords.append(character)

    filtered_feature_tags = apply_precision_filter(
        feature_tags=list(record.get("feature_tags", [])),
        tag_to_category=tag_to_category,
        mutually_exclusive_groups=mutually_exclusive_groups,
        max_tags_per_category=max_tags_per_category,
        blocked_tags=blocked_tags,
    )
    ordered_feature_tags = sort_feature_tags_for_display(
        feature_tags=filtered_feature_tags,
        tag_to_category=tag_to_category,
        category_rank=category_rank,
        tag_rank=tag_rank,
    )
    for feature_tag in ordered_feature_tags:
        feature_name = tag_to_zh.get(feature_tag, feature_tag)
        if feature_name and feature_name not in keywords:
            keywords.append(feature_name)

    for game in record.get("source_game", []):
        game_name = str(game or "").strip()
        if game_name and game_name not in keywords:
            keywords.append(game_name)

    return keywords


def find_exiftool_binary(exiftool_dir: Path) -> Path | None:
    """Find available exiftool binary.

    Args:
        exiftool_dir: Local tool directory.

    Returns:
        Path to exiftool or None.
    """
    path_binary = shutil.which("exiftool")
    if path_binary:
        return Path(path_binary)

    candidates = [
        exiftool_dir / "exiftool.exe",
        exiftool_dir / "exiftool(-k).exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def download_exiftool_windows(exiftool_dir: Path) -> Path:
    """Download portable exiftool for Windows.

    Args:
        exiftool_dir: Destination directory.

    Returns:
        Downloaded exiftool executable path.
    """
    exiftool_dir.mkdir(parents=True, exist_ok=True)

    homepage = requests.get("https://exiftool.org/", timeout=20).text
    zip_names = re.findall(r"exiftool-\d+\.\d+_64\.zip", homepage)

    if not zip_names:
        raise RuntimeError("无法在 exiftool 官网解析到 Windows 64 位下载包。")

    package_name = sorted(set(zip_names))[-1]
    zip_url = f"https://exiftool.org/{package_name}"
    zip_path = exiftool_dir / package_name

    response = requests.get(zip_url, timeout=60)
    response.raise_for_status()
    zip_path.write_bytes(response.content)

    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(exiftool_dir)

    final_binary = exiftool_dir / "exiftool.exe"
    extracted_binary = next(exiftool_dir.rglob("exiftool.exe"), None)
    if extracted_binary is None:
        extracted_binary = next(exiftool_dir.rglob("exiftool(-k).exe"), None)
    if extracted_binary is None:
        raise RuntimeError("已下载 exiftool，但未找到可执行文件。")

    if extracted_binary.resolve() != final_binary.resolve():
        if final_binary.exists():
            final_binary.unlink()
        extracted_binary.rename(final_binary)

    extracted_lib_dir = next(exiftool_dir.rglob("exiftool_files"), None)
    target_lib_dir = exiftool_dir / "exiftool_files"
    if extracted_lib_dir is None:
        raise RuntimeError("已下载 exiftool，但未找到 exiftool_files 依赖目录。")
    if extracted_lib_dir.resolve() != target_lib_dir.resolve():
        if target_lib_dir.exists():
            shutil.rmtree(target_lib_dir)
        extracted_lib_dir.rename(target_lib_dir)

    return final_binary


def ensure_exiftool(exiftool_dir: Path) -> Path:
    """Ensure an executable exiftool exists.

    Args:
        exiftool_dir: Local tool directory.

    Returns:
        Exiftool executable path.
    """
    found = find_exiftool_binary(exiftool_dir)
    if found:
        return found
    return download_exiftool_windows(exiftool_dir)


def write_keywords_with_exiftool(
    exiftool_path: Path,
    image_path: Path,
    keywords: list[str],
) -> None:
    """Write keywords into multiple metadata fields.

    Args:
        exiftool_path: Exiftool binary path.
        image_path: Target image path.
        keywords: Chinese keywords.
    """
    joined = "; ".join(keywords)
    args_lines = [
        "-overwrite_original",
        "-P",
        "-m",
        "-sep",
        "; ",
        "-charset",
        "exiftool=utf8",
        f"-XMP-dc:Subject={joined}",
    ]

    if image_path.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff"}:
        args_lines.append(f"-XPKeywords={joined}")

    args_lines.append(str(image_path))

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".args", delete=False) as temp_args_file:
        temp_args_path = Path(temp_args_file.name)
        temp_args_file.write("\n".join(args_lines) + "\n")

    command = [str(exiftool_path), "-@", str(temp_args_path)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    finally:
        if temp_args_path.exists():
            temp_args_path.unlink()


def build_target_records(
    records: Iterable[dict],
    status_filter: set[str],
) -> list[dict]:
    """Filter records by status and image extension.

    Args:
        records: Input records.
        status_filter: Accepted status values.

    Returns:
        Filtered records.
    """
    filtered: list[dict] = []
    for record in records:
        status = record.get("status", "")
        image_path = str(record.get("image_path", ""))
        extension = Path(image_path).suffix.lower()

        if status_filter and status not in status_filter:
            continue
        if extension not in SUPPORTED_EXTENSIONS:
            continue
        filtered.append(record)
    return filtered


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Write localized tags into image metadata keywords.")
    parser.add_argument(
        "--queue",
        default=str(DEFAULT_QUEUE),
        help="Input annotation queue JSONL.",
    )
    parser.add_argument(
        "--taxonomy",
        default=str(DEFAULT_TAXONOMY),
        help="Feature taxonomy JSON.",
    )
    parser.add_argument(
        "--priority-rules",
        default=str(DEFAULT_PRIORITY_RULES),
        help="Feature priority rules JSON.",
    )
    parser.add_argument(
        "--sensitive-terms",
        default=str(DEFAULT_SENSITIVE_TERMS),
        help="Optional sensitive terms extension JSON.",
    )
    parser.add_argument(
        "--image-root",
        default=".",
        help="Project root for resolving image_path.",
    )
    parser.add_argument(
        "--status",
        default="labeled_draft",
        help="Comma-separated statuses to write, e.g. labeled_draft,approved.",
    )
    parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        help="Metadata language code, e.g. zh-CN/en-US/ja-JP/ko-KR.",
    )
    parser.add_argument(
        "--exiftool-dir",
        default=str(DEFAULT_EXIFTOOL_DIR),
        help="Local directory to store exiftool when not installed.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    queue_path = Path(args.queue).resolve()
    taxonomy_path = Path(args.taxonomy).resolve()
    priority_rules_path = Path(args.priority_rules).resolve()
    sensitive_terms_path = Path(args.sensitive_terms).resolve() if str(args.sensitive_terms).strip() else None
    image_root = Path(args.image_root).resolve()
    exiftool_dir = Path(args.exiftool_dir).resolve()
    language_code = normalize_language_code(str(args.language).strip() or DEFAULT_LANGUAGE)
    status_filter = {item.strip() for item in args.status.split(",") if item.strip()}

    records = parse_jsonl(queue_path)
    target_records = build_target_records(records=records, status_filter=status_filter)
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
        image_rel_path = Path(record["image_path"])
        image_abs_path = (image_root / image_rel_path).resolve()
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

    print(f"Exiftool: {exiftool_path}")
    print(f"Target records: {len(target_records)}")
    print(f"Updated files: {updated}")
    print(f"Skipped files: {skipped}")


if __name__ == "__main__":
    main()
