"""Automatically recognize anime tags and write localized metadata keywords."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import onnxruntime as ort
import requests
from PIL import Image

try:
    from scripts.write_tags_to_image_metadata import (
        build_target_records,
        ensure_exiftool,
        load_blocked_tags,
        load_display_priority,
        load_max_tags_per_category,
        load_sensitive_terms_payload,
        load_taxonomy_map,
        load_taxonomy_structure,
        normalize_keywords,
        write_keywords_with_exiftool,
    )
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
    from core.moegirl_tagger.custom_character_store import CustomCharacterStore, select_localized_alias
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.write_tags_to_image_metadata import (
        build_target_records,
        ensure_exiftool,
        load_blocked_tags,
        load_display_priority,
        load_max_tags_per_category,
        load_sensitive_terms_payload,
        load_taxonomy_map,
        load_taxonomy_structure,
        normalize_keywords,
        write_keywords_with_exiftool,
    )
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
    from core.moegirl_tagger.custom_character_store import CustomCharacterStore, select_localized_alias

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
DEFAULT_IMAGE_DIR = Path("image")
DEFAULT_OUTPUT_QUEUE = Path("data/annotation_queue/pending_annotations.jsonl")
DEFAULT_TAXONOMY = Path("data/character_library/feature_taxonomy.json")
DEFAULT_SYNONYMS = Path("data/character_library/feature_synonyms.json")
DEFAULT_PRIORITY_RULES = Path("data/character_library/feature_priority_rules.json")
DEFAULT_SENSITIVE_TERMS = Path("data/character_library/sensitive_terms.json")
DEFAULT_CUSTOM_CHARACTERS_DIR = Path("data/character_library/custom")
DEFAULT_MODEL_DIR = Path("tools/wd14")
DEFAULT_EXIFTOOL_DIR = Path("tools/exiftool")

MODEL_URL = "https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2/resolve/main/model.onnx"
TAGS_URL = "https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2/resolve/main/selected_tags.csv"

COPYRIGHT_GAME_MAP = {
    "genshin_impact": "genshin_impact",
    "zenless_zone_zero": "zenless_zone_zero",
    "zzz": "zenless_zone_zero",
}


def normalize_token(value: str) -> str:
    """Normalize text for matching.

    Args:
        value: Raw token.

    Returns:
        Normalized token for matching.
    """
    lowered = value.strip().lower().replace("-", "_")
    lowered = lowered.replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", lowered)


def ensure_parent(path: Path) -> None:
    """Ensure parent directory exists.

    Args:
        path: File path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def download_file(url: str, target_path: Path) -> None:
    """Download a file to disk.

    Args:
        url: File URL.
        target_path: Output path.
    """
    ensure_parent(target_path)
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with target_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def ensure_model_assets(model_dir: Path) -> tuple[Path, Path]:
    """Ensure WD14 ONNX model and selected tags are available.

    Args:
        model_dir: Local model directory.

    Returns:
        Tuple of (model_path, tags_csv_path).
    """
    model_path = model_dir / "model.onnx"
    tags_path = model_dir / "selected_tags.csv"

    if not model_path.exists():
        download_file(MODEL_URL, model_path)
    if not tags_path.exists():
        download_file(TAGS_URL, tags_path)

    return model_path, tags_path


def parse_tag_category(raw_value: str) -> str:
    """Convert CSV category value into semantic group.

    Args:
        raw_value: Raw category from selected_tags.csv.

    Returns:
        Category kind.
    """
    value = str(raw_value).strip().lower()
    if value in {"4", "character"}:
        return "character"
    if value in {"3", "copyright"}:
        return "copyright"
    if value in {"9", "rating"}:
        return "rating"
    return "general"


@dataclass
class ModelTag:
    """One model output tag with score and category."""

    name: str
    category: str
    score: float


class WD14Tagger:
    """WD14 ONNX tagger wrapper."""

    def __init__(self, model_path: Path, tags_path: Path) -> None:
        self.model_path = model_path
        self.tags_path = tags_path
        self.tags = self._load_tags(tags_path)
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        input_shape = self.session.get_inputs()[0].shape
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.model_height = int(input_shape[1]) if input_shape[1] else 448
        self.model_width = int(input_shape[2]) if input_shape[2] else 448

    @staticmethod
    def _load_tags(tags_path: Path) -> list[tuple[str, str]]:
        tags: list[tuple[str, str]] = []
        with tags_path.open("r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                tag_name = str(row.get("name", "")).strip()
                if not tag_name:
                    continue
                category = parse_tag_category(str(row.get("category", "")))
                tags.append((tag_name, category))
        return tags

    def _prepare_input(self, image_path: Path) -> np.ndarray:
        image = Image.open(image_path).convert("RGB")
        rgb = np.asarray(image, dtype=np.uint8)
        h, w = rgb.shape[:2]
        side = max(h, w)

        padded = np.full((side, side, 3), 255, dtype=np.uint8)
        offset_y = (side - h) // 2
        offset_x = (side - w) // 2
        padded[offset_y:offset_y + h, offset_x:offset_x + w] = rgb

        pil_resized = Image.fromarray(padded, mode="RGB").resize(
            (self.model_width, self.model_height),
            Image.Resampling.BICUBIC,
        )
        resized_rgb = np.asarray(pil_resized, dtype=np.float32)
        resized_bgr = resized_rgb[:, :, ::-1]
        batch = np.expand_dims(resized_bgr, axis=0)
        return batch

    def _predict_scores(self, image_path: Path) -> np.ndarray:
        """Run model and return raw score vector."""
        input_tensor = self._prepare_input(image_path)
        outputs = self.session.run([self.output_name], {self.input_name: input_tensor})[0]
        return np.asarray(outputs[0], dtype=np.float32)

    def predict_with_vector(self, image_path: Path) -> tuple[list[ModelTag], np.ndarray]:
        """Run inference and return structured tags with raw vector."""
        score_vector = self._predict_scores(image_path)
        scores = score_vector.astype(float).tolist()
        count = min(len(scores), len(self.tags))

        result: list[ModelTag] = []
        for index in range(count):
            tag_name, category = self.tags[index]
            result.append(ModelTag(name=tag_name, category=category, score=scores[index]))
        return result, score_vector

    def predict(self, image_path: Path) -> list[ModelTag]:
        """Run tag inference for one image.

        Args:
            image_path: Input image path.

        Returns:
            Predicted tags with categories and scores.
        """
        tags, _ = self.predict_with_vector(image_path)
        return tags


def load_feature_resources(
    taxonomy_path: Path,
    synonyms_path: Path,
    sensitive_terms_path: Path | None = None,
) -> tuple[set[str], dict[str, str]]:
    """Load canonical feature ids and alias normalization map.

    Args:
        taxonomy_path: Taxonomy JSON path.
        synonyms_path: Synonyms JSON path.

    Returns:
        Tuple of (valid feature tags, alias->canonical map).
    """
    synonyms = json.loads(synonyms_path.read_text(encoding="utf-8"))
    sensitive_payload = load_sensitive_terms_payload(
        reference_path=synonyms_path,
        sensitive_terms_path=sensitive_terms_path,
    )

    valid_tags = set(load_taxonomy_map(taxonomy_path, sensitive_terms_path=sensitive_terms_path).keys())

    merged_canonical_to_aliases: dict[str, list[str]] = {}
    for mapping in (
        synonyms.get("canonical_to_aliases", {}),
        sensitive_payload.get("synonyms", {}).get("canonical_to_aliases", {}),
    ):
        if not isinstance(mapping, dict):
            continue
        for canonical, aliases in mapping.items():
            canonical_id = str(canonical).strip()
            if not canonical_id:
                continue
            bucket = merged_canonical_to_aliases.setdefault(canonical_id, [])
            if not isinstance(aliases, list):
                continue
            for alias in aliases:
                alias_text = str(alias).strip()
                if alias_text and alias_text not in bucket:
                    bucket.append(alias_text)

    merged_deprecated: dict[str, str] = {}
    for mapping in (
        synonyms.get("deprecated_tags", {}),
        sensitive_payload.get("synonyms", {}).get("deprecated_tags", {}),
    ):
        if not isinstance(mapping, dict):
            continue
        for old_tag, new_tag in mapping.items():
            old_text = str(old_tag).strip()
            new_text = str(new_tag).strip()
            if old_text and new_text:
                merged_deprecated[old_text] = new_text

    alias_map: dict[str, str] = {}
    for canonical, aliases in merged_canonical_to_aliases.items():
        canonical_id = str(canonical)
        if canonical_id not in valid_tags:
            continue
        alias_map[normalize_token(canonical_id)] = canonical_id
        for alias in aliases:
            normalized_alias = normalize_token(str(alias))
            if normalized_alias:
                alias_map[normalized_alias] = canonical_id

    for old_tag, new_tag in merged_deprecated.items():
        canonical_id = str(new_tag)
        if canonical_id not in valid_tags:
            continue
        alias_map[normalize_token(str(old_tag))] = canonical_id

    return valid_tags, alias_map


def detect_source_game(
    copyright_tags: Iterable[str],
) -> list[str]:
    """Detect source game list.

    Args:
        copyright_tags: Copyright tags from model.

    Returns:
        Distinct source game ids.
    """
    result: list[str] = []

    for raw_tag in copyright_tags:
        normalized = normalize_token(raw_tag)
        game = COPYRIGHT_GAME_MAP.get(normalized)
        if game and game not in result:
            result.append(game)

    return result


def canonicalize_feature_tags(
    predicted_tags: Iterable[ModelTag],
    alias_map: dict[str, str],
    min_score: float,
    blocked_tags: set[str] | None = None,
    tag_to_category: dict[str, str] | None = None,
    category_min_scores: dict[str, float] | None = None,
    tag_min_scores: dict[str, float] | None = None,
) -> list[str]:
    """Convert predicted model tags to canonical feature tags.

    Args:
        predicted_tags: Model output tags.
        alias_map: Alias to canonical mapping.
        min_score: Minimum score for accepted feature tags.
        blocked_tags: Hard-blocked canonical tags.
        tag_to_category: Canonical tag -> category mapping.
        category_min_scores: Category-specific minimum score mapping.
        tag_min_scores: Canonical tag-specific minimum score mapping.

    Returns:
        Ordered canonical feature tags.
    """
    result: list[str] = []
    seen: set[str] = set()
    blocked = blocked_tags if blocked_tags else set()

    sorted_tags = sorted(predicted_tags, key=lambda item: item.score, reverse=True)
    for tag in sorted_tags:
        if tag.category not in {"general", "rating"}:
            continue
        normalized = normalize_token(tag.name)
        canonical = alias_map.get(normalized)
        if not canonical:
            continue
        required_score = min_score
        if tag_to_category and category_min_scores:
            category = tag_to_category.get(canonical, "")
            if category:
                required_score = category_min_scores.get(category, min_score)
        if tag_min_scores and canonical in tag_min_scores:
            required_score = tag_min_scores[canonical]
        if tag.score < required_score:
            continue
        if canonical in blocked:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


def build_custom_character_index(
    store: CustomCharacterStore,
    tagger: WD14Tagger,
    preferred_language: str = "zh-CN",
) -> CharacterVectorIndex | None:
    """Build custom-character vector index from reference images.

    Args:
        store: Custom character store.
        tagger: WD14 tagger used to extract vectors.
        preferred_language: Preferred UI language for character label selection.

    Returns:
        Built index or None when no valid references.
    """
    reference_items = store.iter_reference_items(enabled_only=True)
    if not reference_items:
        return None

    embeddings: list[np.ndarray] = []
    character_ids: list[str] = []
    character_names: list[str] = []
    image_paths: list[str] = []
    for record, image_path in reference_items:
        try:
            _, vector = tagger.predict_with_vector(image_path)
        except Exception:
            continue
        embeddings.append(np.asarray(vector, dtype=np.float32).reshape(-1))
        character_ids.append(str(record.get("id", "")).strip())
        character_names.append(select_localized_alias(record, preferred_language))
        image_paths.append(image_path.as_posix())

    if not embeddings:
        return None

    matrix = np.stack(embeddings).astype(np.float32)
    index = CharacterVectorIndex(
        embeddings=matrix,
        character_ids=character_ids,
        character_names=character_names,
        image_paths=image_paths,
    )
    index.save(store.root / "index.npz", store.root / "index_meta.json")
    return index


def resolve_custom_characters(
    query_vector: np.ndarray,
    custom_index: CharacterVectorIndex | None,
    min_similarity: float,
    top_k: int = 1,
    min_margin: float = 0.0,
) -> list[str]:
    """Resolve custom character names using vector retrieval."""
    if custom_index is None:
        return []
    safe_top_k = max(1, int(top_k))
    matches = custom_index.query_many(
        query_vector=query_vector,
        min_similarity=0.0,
        top_k=max(10, safe_top_k * 4),
    )
    if not matches:
        return []

    best_by_name: dict[str, float] = {}
    for match in matches:
        name = str(match.character_name).strip()
        if not name:
            continue
        score = float(match.similarity)
        previous = best_by_name.get(name)
        if previous is None or score > previous:
            best_by_name[name] = score
    if not best_by_name:
        return []

    ranked = sorted(best_by_name.items(), key=lambda item: item[1], reverse=True)
    best_name, best_score = ranked[0]
    _ = best_name
    if best_score < float(min_similarity):
        return []
    if len(ranked) >= 2:
        second_score = float(ranked[1][1])
        if (best_score - second_score) < float(min_margin):
            return []
    names = [name for name, score in ranked if float(score) >= float(min_similarity)]
    return names[:safe_top_k]


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


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Auto-recognize image tags and write metadata.")
    parser.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR), help="Image directory.")
    parser.add_argument("--queue-output", default=str(DEFAULT_OUTPUT_QUEUE), help="Output queue JSONL.")
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY), help="Feature taxonomy JSON.")
    parser.add_argument("--synonyms", default=str(DEFAULT_SYNONYMS), help="Feature synonyms JSON.")
    parser.add_argument("--priority-rules", default=str(DEFAULT_PRIORITY_RULES), help="Priority rules JSON.")
    parser.add_argument(
        "--sensitive-terms",
        default=str(DEFAULT_SENSITIVE_TERMS),
        help="Optional sensitive terms extension JSON.",
    )
    parser.add_argument(
        "--custom-character-dir",
        default=str(DEFAULT_CUSTOM_CHARACTERS_DIR),
        help="Custom character library directory.",
    )
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR), help="WD14 model directory.")
    parser.add_argument("--exiftool-dir", default=str(DEFAULT_EXIFTOOL_DIR), help="Exiftool directory.")
    parser.add_argument(
        "--input-list",
        default="",
        help="Optional text file with one image path per line. Overrides --image-dir scanning.",
    )
    parser.add_argument("--feature-threshold", type=float, default=0.62, help="Feature score threshold.")
    parser.add_argument(
        "--adult-feature-threshold",
        type=float,
        default=0.55,
        help="Score threshold used for adult_content tags.",
    )
    parser.add_argument(
        "--footwear-feature-threshold",
        type=float,
        default=0.50,
        help="Score threshold used for footwear tags.",
    )
    parser.add_argument(
        "--barefoot-feature-threshold",
        type=float,
        default=0.35,
        help="Score threshold used for barefoot tag.",
    )
    parser.add_argument(
        "--custom-character-threshold",
        type=float,
        default=0.55,
        help="Similarity threshold for custom character retrieval.",
    )
    parser.add_argument(
        "--custom-character-margin",
        type=float,
        default=0.12,
        help="Minimum top1-top2 similarity gap required for accepting a custom character.",
    )
    parser.add_argument(
        "--custom-character-topk",
        type=int,
        default=1,
        help="Maximum custom character candidates per image.",
    )
    parser.add_argument(
        "--custom-character-language",
        default="zh-CN",
        help="Preferred language code for custom character names (e.g. zh-CN/en-US/ja-JP).",
    )
    parser.add_argument("--copyright-threshold", type=float, default=0.70, help="Copyright score threshold.")
    parser.add_argument("--non-recursive", action="store_true", help="Disable recursive image scanning.")
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    root = Path.cwd().resolve()
    image_dir = (root / args.image_dir).resolve()
    queue_output = (root / args.queue_output).resolve()
    taxonomy_path = (root / args.taxonomy).resolve()
    synonyms_path = (root / args.synonyms).resolve()
    priority_rules_path = (root / args.priority_rules).resolve()
    sensitive_terms_path = (root / args.sensitive_terms).resolve() if str(args.sensitive_terms).strip() else None
    custom_character_dir = (root / args.custom_character_dir).resolve()
    model_dir = (root / args.model_dir).resolve()
    exiftool_dir = (root / args.exiftool_dir).resolve()

    model_path, tags_path = ensure_model_assets(model_dir)
    tagger = WD14Tagger(model_path=model_path, tags_path=tags_path)
    _, alias_map = load_feature_resources(
        taxonomy_path=taxonomy_path,
        synonyms_path=synonyms_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    tag_to_category, _ = load_taxonomy_structure(
        taxonomy_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    blocked_tags = load_blocked_tags(
        priority_rules_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    custom_store = CustomCharacterStore(custom_character_dir)
    custom_index = build_custom_character_index(
        store=custom_store,
        tagger=tagger,
        preferred_language=str(args.custom_character_language).strip() or "zh-CN",
    )

    if args.input_list:
        input_list_path = (root / args.input_list).resolve()
        images = collect_images_from_list(list_path=input_list_path, root_dir=root)
    else:
        images = collect_images(image_dir=image_dir, recursive=not args.non_recursive)
    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()
    records: list[dict] = []

    for image_path in images:
        predicted, score_vector = tagger.predict_with_vector(image_path)
        feature_tags = canonicalize_feature_tags(
            predicted_tags=predicted,
            alias_map=alias_map,
            min_score=args.feature_threshold,
            blocked_tags=blocked_tags,
            tag_to_category=tag_to_category,
            category_min_scores={
                "adult_content": args.adult_feature_threshold,
                "footwear": args.footwear_feature_threshold,
            },
            tag_min_scores={"barefoot": args.barefoot_feature_threshold},
        )
        characters = resolve_custom_characters(
            query_vector=score_vector,
            custom_index=custom_index,
            min_similarity=args.custom_character_threshold,
            top_k=max(1, int(args.custom_character_topk)),
            min_margin=max(0.0, float(args.custom_character_margin)),
        )
        copyright_tags = [
            tag.name
            for tag in predicted
            if tag.category == "copyright" and tag.score >= args.copyright_threshold
        ]
        source_game = detect_source_game(copyright_tags=copyright_tags)

        record = build_record(
            image_path=image_path,
            root_path=root,
            characters=characters,
            feature_tags=feature_tags,
            source_game=source_game,
            now_iso=now_iso,
        )
        records.append(record)

    written = write_jsonl(queue_output, records)
    target, updated, skipped = process_and_write_metadata(
        queue_path=queue_output,
        image_root=root,
        taxonomy_path=taxonomy_path,
        priority_rules_path=priority_rules_path,
        exiftool_dir=exiftool_dir,
        sensitive_terms_path=sensitive_terms_path,
        metadata_language=str(args.custom_character_language).strip() or "zh-CN",
    )

    print(f"Images found: {len(images)}")
    print(f"Queue written: {written}")
    print(f"Metadata targets: {target}")
    print(f"Metadata updated: {updated}")
    print(f"Metadata skipped: {skipped}")


if __name__ == "__main__":
    main()
