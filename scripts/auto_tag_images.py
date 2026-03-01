"""Automatically recognize anime tags and write localized metadata keywords."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
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

# Prioritize head/face region for character retrieval while keeping
# full-image query as a lower-weight fallback.
FULL_IMAGE_CHARACTER_WEIGHT = 0.60
MIN_CHARACTER_REGION_SIDE = 96
CHARACTER_REGION_SPECS: tuple[tuple[str, tuple[float, float, float, float], float], ...] = (
    ("head_center", (0.20, 0.00, 0.80, 0.60), 1.00),
    ("head_left", (0.00, 0.00, 0.65, 0.70), 0.95),
    ("head_right", (0.35, 0.00, 1.00, 0.70), 0.95),
)
DEFAULT_MULTI_CHARACTER_THRESHOLD_FLOOR = 0.48
MAX_HEAD_QUERY_REGIONS = 3
MAX_HEAD_CANDIDATE_EVAL_SINGLE = 12
MAX_HEAD_CANDIDATE_EVAL_MULTI = 16
HEAD_CANDIDATE_FALLBACK_EVAL_SINGLE = 8
HEAD_CANDIDATE_FALLBACK_EVAL_MULTI = 10
HEAD_FALLBACK_TRIGGER_SCORE = 0.30
HEAD_SCORE_MIN_THRESHOLD = 0.22
HEAD_NMS_IOU_THRESHOLD = 0.28
HEAD_VECTOR_DUPLICATE_SIMILARITY = 0.985
MULTI_CHARACTER_SECONDARY_SCORE_RATIO = 0.70
MIN_CHARACTER_MATCH_CANDIDATES = 96
MULTI_CHARACTER_REGION_REUSE_MAX_SCORE_RATIO = 0.92
SINGLE_REFERENCE_MULTI_SCORE_FACTOR = 0.93
LARGE_CHARACTER_LIBRARY_ROWS = 1000
HUGE_CHARACTER_LIBRARY_ROWS = 2000
LARGE_LIBRARY_SECONDARY_RATIO_DELTA = 0.04
HUGE_LIBRARY_SECONDARY_RATIO_DELTA = 0.06
HEAD_BASE_REGION_SPECS: tuple[tuple[float, float, float, float], ...] = (
    (0.00, 0.00, 1.00, 0.72),
    (0.00, 0.00, 0.62, 0.72),
    (0.38, 0.00, 1.00, 0.72),
    (0.18, 0.00, 0.82, 0.74),
    (0.00, 0.05, 0.55, 0.78),
    (0.45, 0.05, 1.00, 0.78),
)
HEAD_PROBE_CENTERS: tuple[float, ...] = (0.18, 0.30, 0.42, 0.54, 0.66, 0.78)
HEAD_PROBE_HALF_WIDTHS: tuple[float, ...] = (0.14, 0.18, 0.22)
HEAD_PROBE_VERTICAL_RANGES: tuple[tuple[float, float], ...] = (
    (0.00, 0.52),
    (0.08, 0.62),
)
HEAD_SIGNAL_TAG_WEIGHTS: dict[str, float] = {
    "portrait": 0.35,
    "upper_body": 0.05,
    "looking_at_viewer": 0.04,
    "face_to_face": 0.03,
    "forehead": 0.12,
    "bangs": 0.14,
    "hair_between_eyes": 0.12,
    "ahoge": 0.18,
    "hair_intakes": 0.20,
    "streaked_hair": 0.18,
    "drill_hair": 0.18,
    "wavy_hair": 0.15,
    "curly_hair": 0.15,
    "multicolored_hair": 0.10,
    "two-tone_hair": 0.10,
    "colored_inner_hair": 0.10,
    "blue_eyes": 0.18,
    "red_eyes": 0.18,
    "green_eyes": 0.18,
    "purple_eyes": 0.18,
    "yellow_eyes": 0.18,
    "pink_eyes": 0.18,
    "brown_eyes": 0.18,
    "orange_eyes": 0.18,
    "aqua_eyes": 0.18,
    "grey_eyes": 0.18,
    "black_eyes": 0.18,
    "multicolored_eyes": 0.24,
    "heterochromia": 0.28,
    "slit_pupils": 0.20,
    "bright_pupils": 0.18,
    "white_pupils": 0.16,
    "constricted_pupils": 0.18,
    "red_pupils": 0.16,
    "blue_pupils": 0.16,
    "yellow_pupils": 0.16,
    "pink_pupils": 0.16,
    "mismatched_pupils": 0.22,
    "horizontal_pupils": 0.16,
    "ringed_eyes": 0.18,
    "eyelashes": 0.12,
    "colored_eyelashes": 0.20,
    "long_eyelashes": 0.16,
    "eyeshadow": 0.16,
    "red_eyeshadow": 0.15,
    "blue_eyeshadow": 0.15,
    "purple_eyeshadow": 0.15,
    "pink_eyeshadow": 0.15,
    "green_eyeshadow": 0.15,
    "facial_mark": 0.24,
    "forehead_mark": 0.22,
    "facepaint": 0.22,
    "tattoo": 0.18,
    "braid": 0.16,
    "single_braid": 0.16,
    "side_braid": 0.15,
    "twin_braids": 0.16,
    "hair_ornament": 0.12,
    "mini_hat": 0.12,
    "hat": 0.08,
}
HEAD_NEGATIVE_TAG_WEIGHTS: dict[str, float] = {
    "faceless": -0.45,
    "head_out_of_frame": -0.45,
    "headless": -0.60,
    "extra_faces": -0.35,
    "no_eyes": -0.40,
    "covered_eyes": -0.25,
    "hair_over_eyes": -0.20,
    "closed_eyes": -0.04,
    "breasts": -0.12,
    "large_breasts": -0.14,
    "huge_breasts": -0.18,
    "breast_press": -0.16,
    "cleavage": -0.10,
    "navel": -0.08,
    "thighs": -0.06,
}
ATTRIBUTE_HAIR_COLOR_TAGS: tuple[str, ...] = (
    "black_hair",
    "blonde_hair",
    "brown_hair",
    "blue_hair",
    "green_hair",
    "grey_hair",
    "orange_hair",
    "pink_hair",
    "purple_hair",
    "red_hair",
    "silver_hair",
    "white_hair",
    "aqua_hair",
)
ATTRIBUTE_EYE_COLOR_TAGS: tuple[str, ...] = (
    "black_eyes",
    "brown_eyes",
    "blue_eyes",
    "green_eyes",
    "grey_eyes",
    "orange_eyes",
    "pink_eyes",
    "purple_eyes",
    "red_eyes",
    "yellow_eyes",
    "aqua_eyes",
)
ATTRIBUTE_STYLE_DETAIL_TAGS: tuple[str, ...] = (
    "hair_intakes",
    "streaked_hair",
    "multicolored_hair",
    "two-tone_hair",
    "colored_inner_hair",
    "ahoge",
    "braid",
    "single_braid",
    "side_braid",
    "twin_braids",
    "drill_hair",
    "wavy_hair",
    "curly_hair",
    "twintails",
    "ponytail",
    "side_ponytail",
)
ATTRIBUTE_FACE_DETAIL_TAGS: tuple[str, ...] = (
    "facial_mark",
    "forehead_mark",
    "facepaint",
    "tattoo",
    "heterochromia",
    "multicolored_eyes",
    "mismatched_pupils",
    "ringed_eyes",
    "colored_eyelashes",
    "eyeshadow",
    "red_eyeshadow",
    "blue_eyeshadow",
    "purple_eyeshadow",
    "pink_eyeshadow",
    "green_eyeshadow",
)
ATTRIBUTE_STRONG_QUERY_SCORE = 0.55
ATTRIBUTE_REFERENCE_MATCH_SCORE = 0.42
ATTRIBUTE_REFERENCE_MISS_SCORE = 0.18
ATTRIBUTE_MAX_ADJUSTMENT = 0.28
ATTRIBUTE_MULTI_PERSON_TAGS: tuple[str, ...] = (
    "multiple_girls",
    "multiple_boys",
    "multiple_boys_and_girls",
    "2girls",
    "3girls",
    "4girls",
    "5girls",
    "2boys",
    "3boys",
)
HAIR_COLOR_GROUP_MAP: dict[str, str] = {
    "black_hair": "neutral_dark",
    "brown_hair": "neutral_dark",
    "grey_hair": "neutral_dark",
    "blonde_hair": "light_neutral",
    "white_hair": "light_neutral",
    "silver_hair": "light_neutral",
    "blue_hair": "cool_blue",
    "aqua_hair": "cool_blue",
    "green_hair": "green_cyan",
    "purple_hair": "magenta_purple",
    "pink_hair": "magenta_purple",
    "red_hair": "warm_red_orange",
    "orange_hair": "warm_red_orange",
    "multicolored_hair": "multi",
    "two-tone_hair": "multi",
    "colored_inner_hair": "multi",
}
EYE_COLOR_GROUP_MAP: dict[str, str] = {
    "black_eyes": "neutral_dark",
    "brown_eyes": "neutral_dark",
    "grey_eyes": "neutral_dark",
    "blue_eyes": "cool_blue",
    "aqua_eyes": "cool_blue",
    "green_eyes": "green_cyan",
    "purple_eyes": "magenta_purple",
    "pink_eyes": "magenta_purple",
    "red_eyes": "warm_red_orange",
    "orange_eyes": "warm_red_orange",
    "yellow_eyes": "warm_red_orange",
    "multicolored_eyes": "multi",
    "heterochromia": "multi",
}
CORRELATION_PROFILE_MIN_SCORE = 0.42
CORRELATION_QUERY_MIN_HAIR_SCORE = 0.58
CORRELATION_QUERY_MIN_EYE_SCORE = 0.58
CORRELATION_PROFILE_SCHEMA_VERSION = 1
CORRELATION_PROFILE_FILE_NAME = "correlation_profiles.json"


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

    def _prepare_input_array(self, image: Image.Image) -> np.ndarray:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
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

    def _prepare_input(self, image_path: Path) -> np.ndarray:
        with Image.open(image_path) as image:
            return self._prepare_input_array(image)

    def _predict_scores(self, image_path: Path) -> np.ndarray:
        """Run model and return raw score vector."""
        input_tensor = self._prepare_input(image_path)
        outputs = self.session.run([self.output_name], {self.input_name: input_tensor})[0]
        return np.asarray(outputs[0], dtype=np.float32)

    def _predict_scores_from_image(self, image: Image.Image) -> np.ndarray:
        """Run model for in-memory image and return raw score vector."""
        input_tensor = self._prepare_input_array(image)
        outputs = self.session.run([self.output_name], {self.input_name: input_tensor})[0]
        return np.asarray(outputs[0], dtype=np.float32)

    def _build_model_tags(self, score_vector: np.ndarray) -> list[ModelTag]:
        scores = score_vector.astype(float).tolist()
        count = min(len(scores), len(self.tags))
        result: list[ModelTag] = []
        for index in range(count):
            tag_name, category = self.tags[index]
            result.append(ModelTag(name=tag_name, category=category, score=scores[index]))
        return result

    def predict_with_vector(self, image_path: Path) -> tuple[list[ModelTag], np.ndarray]:
        """Run inference and return structured tags with raw vector."""
        score_vector = self._predict_scores(image_path)
        return self._build_model_tags(score_vector), score_vector

    def predict_with_vector_from_image(self, image: Image.Image) -> tuple[list[ModelTag], np.ndarray]:
        """Run inference for in-memory image and return structured tags with raw vector."""
        score_vector = self._predict_scores_from_image(image)
        return self._build_model_tags(score_vector), score_vector

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


def infer_character_count(predicted_tags: Iterable[ModelTag], min_score: float = 0.35, max_count: int = 3) -> int:
    """Infer likely character count from WD14 general-count tags."""
    explicit_count = 0
    has_multiple_flag = False
    threshold = max(0.0, float(min_score))

    for tag in predicted_tags:
        if str(tag.category).strip() != "general":
            continue
        score = float(tag.score)
        if score < threshold:
            continue
        name = normalize_token(tag.name)
        count_match = re.match(r"^(\d+)(girl|girls|boy|boys)$", name)
        if count_match:
            try:
                explicit_count = max(explicit_count, int(count_match.group(1)))
            except Exception:
                pass
            continue
        if name in {"multiple_girls", "multiple_boys", "multiple_boys_and_girls"}:
            has_multiple_flag = True

    inferred = explicit_count
    if inferred <= 0:
        inferred = 3 if has_multiple_flag else 1

    safe_max = max(1, int(max_count))
    return max(1, min(inferred, safe_max))


def resolve_effective_character_threshold(base_threshold: float, inferred_count: int, multi_floor: float) -> float:
    """Resolve similarity threshold for character retrieval.

    For multi-character scenes, allow a lower threshold floor to improve
    recall for each individual face/region match.
    """
    base = max(0.0, float(base_threshold))
    if int(inferred_count) <= 1:
        return base
    floor = max(0.0, float(multi_floor))
    return min(base, floor)


def resolve_effective_character_top_k(base_top_k: int, inferred_count: int, detected_head_count: int) -> int:
    """Resolve final character top-k with head-count guard."""
    base = max(1, int(base_top_k))
    inferred = max(1, int(inferred_count))
    detected = max(0, int(detected_head_count))
    if detected <= 0:
        return base
    return max(base, min(inferred, detected))


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
    index._correlation_profile_path = store.root / CORRELATION_PROFILE_FILE_NAME  # type: ignore[attr-defined]
    return index


def load_or_build_custom_character_index(
    store: CustomCharacterStore,
    tagger: WD14Tagger,
    preferred_language: str = "zh-CN",
    rebuild: bool = False,
) -> CharacterVectorIndex | None:
    """Load cached custom-character index when available, otherwise rebuild."""
    index_path = store.root / "index.npz"
    meta_path = store.root / "index_meta.json"
    if not bool(rebuild) and index_path.exists():
        try:
            index = CharacterVectorIndex.load(
                index_path=index_path,
                meta_path=meta_path if meta_path.exists() else None,
            )
            index._correlation_profile_path = store.root / CORRELATION_PROFILE_FILE_NAME  # type: ignore[attr-defined]
            return index
        except Exception:
            pass
    return build_custom_character_index(
        store=store,
        tagger=tagger,
        preferred_language=preferred_language,
    )


def _normalized_crop_box(
    width: int,
    height: int,
    left_ratio: float,
    top_ratio: float,
    right_ratio: float,
    bottom_ratio: float,
) -> tuple[int, int, int, int] | None:
    if width <= 0 or height <= 0:
        return None

    left = max(0, min(width - 1, int(round(width * left_ratio))))
    top = max(0, min(height - 1, int(round(height * top_ratio))))
    right = max(left + 1, min(width, int(round(width * right_ratio))))
    bottom = max(top + 1, min(height, int(round(height * bottom_ratio))))
    if right - left < MIN_CHARACTER_REGION_SIDE or bottom - top < MIN_CHARACTER_REGION_SIDE:
        return None
    return left, top, right, bottom


def _box_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = float((right - left) * (bottom - top))
    first_area = float(max(1, (first[2] - first[0]) * (first[3] - first[1])))
    second_area = float(max(1, (second[2] - second[0]) * (second[3] - second[1])))
    union = max(1e-6, first_area + second_area - intersection)
    return intersection / union


def _cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    left = np.asarray(first, dtype=np.float32).reshape(-1)
    right = np.asarray(second, dtype=np.float32).reshape(-1)
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return 0.0
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return float(np.dot(left / left_norm, right / right_norm))


def _tag_score_from_vector(vector: np.ndarray, tag_index: dict[str, int], tag_name: str) -> float:
    index = tag_index.get(tag_name)
    if index is None:
        return 0.0
    idx = int(index)
    if idx < 0 or idx >= vector.size:
        return 0.0
    score = float(vector[idx])
    if score <= 0.0:
        return 0.0
    return min(1.0, score)


def _group_from_tag(tag_name: str, group_map: dict[str, str] | None) -> str:
    if not group_map:
        return ""
    return str(group_map.get(tag_name, "")).strip()


def _exclusive_attribute_adjustment(
    query_vector: np.ndarray,
    reference_vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: tuple[str, ...],
    match_bonus: float,
    conflict_penalty: float,
    group_map: dict[str, str] | None = None,
) -> float:
    available = [name for name in candidates if name in tag_index]
    if len(available) < 2:
        return 0.0

    query_scores = np.asarray(
        [_tag_score_from_vector(query_vector, tag_index, name) for name in available],
        dtype=np.float32,
    )
    query_best_idx = int(np.argmax(query_scores))
    query_best_score = float(query_scores[query_best_idx])
    if query_best_score < ATTRIBUTE_STRONG_QUERY_SCORE:
        return 0.0

    query_second_score = 0.0
    if query_scores.size >= 2:
        sorted_scores = np.sort(query_scores)
        query_second_score = float(sorted_scores[-2])
    query_confidence = max(0.0, query_best_score - query_second_score)
    if query_confidence < 0.10:
        return 0.0

    reference_scores = np.asarray(
        [_tag_score_from_vector(reference_vector, tag_index, name) for name in available],
        dtype=np.float32,
    )
    reference_best_idx = int(np.argmax(reference_scores))
    reference_best_score = float(reference_scores[reference_best_idx])
    if reference_best_score < ATTRIBUTE_REFERENCE_MATCH_SCORE:
        return 0.0

    query_best_name = str(available[query_best_idx])
    reference_best_name = str(available[reference_best_idx])
    if reference_best_idx == query_best_idx:
        return float(match_bonus) * min(query_best_score, reference_best_score)

    query_group = _group_from_tag(query_best_name, group_map)
    reference_group = _group_from_tag(reference_best_name, group_map)
    if query_group and reference_group and query_group == reference_group:
        return float(match_bonus) * min(query_best_score, reference_best_score) * 0.80
    if query_group == "multi" or reference_group == "multi":
        return 0.0

    disagreement = min(query_best_score, reference_best_score)
    return -float(conflict_penalty) * disagreement * min(1.0, query_confidence + 0.35)


def _detail_attribute_adjustment(
    query_vector: np.ndarray,
    reference_vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: tuple[str, ...],
    match_bonus: float,
    miss_penalty: float,
    query_min_score: float = ATTRIBUTE_STRONG_QUERY_SCORE,
    reference_match_score: float = ATTRIBUTE_REFERENCE_MATCH_SCORE,
    reference_miss_score: float = ATTRIBUTE_REFERENCE_MISS_SCORE,
) -> float:
    adjustment = 0.0
    for name in candidates:
        query_score = _tag_score_from_vector(query_vector, tag_index, name)
        if query_score < float(query_min_score):
            continue
        reference_score = _tag_score_from_vector(reference_vector, tag_index, name)
        if reference_score >= float(reference_match_score):
            adjustment += float(match_bonus) * min(query_score, reference_score)
            continue
        if reference_score <= float(reference_miss_score):
            adjustment -= float(miss_penalty) * query_score
    return adjustment


def _attribute_score_adjustment(
    query_vector: np.ndarray,
    reference_vector: np.ndarray,
    tag_index: dict[str, int] | None,
) -> float:
    """Adjust retrieval score using high-discriminative face/hair attributes."""
    if not tag_index:
        return 0.0

    query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
    reference = np.asarray(reference_vector, dtype=np.float32).reshape(-1)
    if query.size == 0 or reference.size == 0 or query.size != reference.size:
        return 0.0

    # Caller already passes normalized WD14 tag index; avoid rebuilding for each match.
    normalized_tag_index = tag_index

    multi_person_score = max(
        (_tag_score_from_vector(query, normalized_tag_index, name) for name in ATTRIBUTE_MULTI_PERSON_TAGS),
        default=0.0,
    )
    scene_conflict_scale = max(0.35, 1.0 - (multi_person_score * 0.75))
    closed_eyes_score = _tag_score_from_vector(query, normalized_tag_index, "closed_eyes")
    eye_conflict_scale = scene_conflict_scale
    if closed_eyes_score >= 0.45:
        eye_conflict_scale *= max(0.25, 1.0 - closed_eyes_score)

    adjustment = 0.0
    adjustment += _exclusive_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_HAIR_COLOR_TAGS,
        match_bonus=0.11,
        conflict_penalty=0.30 * scene_conflict_scale,
        group_map=HAIR_COLOR_GROUP_MAP,
    )
    adjustment += _exclusive_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_EYE_COLOR_TAGS,
        match_bonus=0.08,
        conflict_penalty=0.22 * eye_conflict_scale,
        group_map=EYE_COLOR_GROUP_MAP,
    )
    adjustment += _detail_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_STYLE_DETAIL_TAGS,
        match_bonus=0.035,
        miss_penalty=0.050 * scene_conflict_scale,
    )
    adjustment += _detail_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_FACE_DETAIL_TAGS,
        match_bonus=0.120,
        miss_penalty=0.120 * scene_conflict_scale,
        query_min_score=0.25,
        reference_match_score=0.28,
        reference_miss_score=0.10,
    )
    return float(max(-ATTRIBUTE_MAX_ADJUSTMENT, min(ATTRIBUTE_MAX_ADJUSTMENT, adjustment)))


@dataclass(frozen=True)
class _CharacterCorrelationProfile:
    hair_groups: frozenset[str]
    eye_groups: frozenset[str]


def _extract_dominant_group(
    vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: tuple[str, ...],
    group_map: dict[str, str],
    min_score: float,
) -> tuple[str, float]:
    best_name = ""
    best_score = 0.0
    for candidate in candidates:
        score = _tag_score_from_vector(vector, tag_index, candidate)
        if score > best_score:
            best_name = str(candidate)
            best_score = score
    if best_score < float(min_score):
        return "", 0.0
    group = _group_from_tag(best_name, group_map)
    if not group:
        return "", 0.0
    return group, best_score


def _tag_index_signature(tag_index: dict[str, int]) -> str:
    hasher = hashlib.sha1()
    for name, index in sorted(tag_index.items(), key=lambda item: item[1]):
        hasher.update(str(name).encode("utf-8"))
        hasher.update(b":")
        hasher.update(str(int(index)).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _character_index_signature(custom_index: CharacterVectorIndex) -> str:
    cached = getattr(custom_index, "_character_index_signature", None)
    if isinstance(cached, str) and cached:
        return cached
    hasher = hashlib.sha1()
    row_count = int(custom_index.embeddings.shape[0]) if custom_index.embeddings.ndim == 2 else 0
    dim_count = int(custom_index.embeddings.shape[1]) if custom_index.embeddings.ndim == 2 else 0
    hasher.update(f"{row_count}:{dim_count}\n".encode("utf-8"))
    for character_id, image_path in zip(custom_index.character_ids, custom_index.image_paths):
        hasher.update(str(character_id).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(image_path).encode("utf-8"))
        hasher.update(b"\n")
    signature = hasher.hexdigest()
    custom_index._character_index_signature = signature  # type: ignore[attr-defined]
    return signature


def _serialize_correlation_profiles(
    profiles: dict[str, _CharacterCorrelationProfile],
) -> dict[str, dict[str, list[str]]]:
    payload: dict[str, dict[str, list[str]]] = {}
    for character_id, profile in profiles.items():
        payload[str(character_id)] = {
            "hair_groups": sorted(str(name) for name in profile.hair_groups if str(name)),
            "eye_groups": sorted(str(name) for name in profile.eye_groups if str(name)),
        }
    return payload


def _deserialize_correlation_profiles(payload: object) -> dict[str, _CharacterCorrelationProfile]:
    if not isinstance(payload, dict):
        return {}
    result: dict[str, _CharacterCorrelationProfile] = {}
    for raw_character_id, raw_value in payload.items():
        character_id = str(raw_character_id).strip()
        if not character_id or not isinstance(raw_value, dict):
            continue
        raw_hair = raw_value.get("hair_groups", [])
        raw_eyes = raw_value.get("eye_groups", [])
        hair_groups = frozenset(str(item).strip() for item in raw_hair if str(item).strip())
        eye_groups = frozenset(str(item).strip() for item in raw_eyes if str(item).strip())
        result[character_id] = _CharacterCorrelationProfile(
            hair_groups=hair_groups,
            eye_groups=eye_groups,
        )
    return result


def _load_correlation_profiles_from_file(
    profile_path: Path,
    expected_tag_signature: str,
    expected_index_signature: str,
) -> dict[str, _CharacterCorrelationProfile] | None:
    if not profile_path.exists():
        return None
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version", 0)) != CORRELATION_PROFILE_SCHEMA_VERSION:
        return None
    if str(payload.get("tag_index_signature", "")).strip() != expected_tag_signature:
        return None
    if str(payload.get("index_signature", "")).strip() != expected_index_signature:
        return None
    profiles = _deserialize_correlation_profiles(payload.get("profiles"))
    if not profiles:
        return None
    return profiles


def _save_correlation_profiles_to_file(
    profile_path: Path,
    profiles: dict[str, _CharacterCorrelationProfile],
    tag_signature: str,
    index_signature: str,
) -> None:
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CORRELATION_PROFILE_SCHEMA_VERSION,
        "tag_index_signature": tag_signature,
        "index_signature": index_signature,
        "build_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        "profiles": _serialize_correlation_profiles(profiles),
    }
    temp_path = profile_path.with_suffix(profile_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(profile_path)


def _build_character_correlation_profiles(
    custom_index: CharacterVectorIndex,
    tag_index: dict[str, int],
) -> dict[str, _CharacterCorrelationProfile]:
    profile_counts: dict[str, dict[str, dict[str, int]]] = {}
    if custom_index.embeddings.ndim != 2:
        return {}
    for row_index, character_id in enumerate(custom_index.character_ids):
        normalized_character_id = str(character_id).strip()
        if not normalized_character_id:
            continue
        vector = np.asarray(custom_index.embeddings[row_index], dtype=np.float32).reshape(-1)
        hair_group, _hair_score = _extract_dominant_group(
            vector=vector,
            tag_index=tag_index,
            candidates=ATTRIBUTE_HAIR_COLOR_TAGS,
            group_map=HAIR_COLOR_GROUP_MAP,
            min_score=CORRELATION_PROFILE_MIN_SCORE,
        )
        eye_group, _eye_score = _extract_dominant_group(
            vector=vector,
            tag_index=tag_index,
            candidates=ATTRIBUTE_EYE_COLOR_TAGS,
            group_map=EYE_COLOR_GROUP_MAP,
            min_score=CORRELATION_PROFILE_MIN_SCORE,
        )
        bucket = profile_counts.setdefault(normalized_character_id, {"hair": {}, "eyes": {}})
        if hair_group:
            bucket["hair"][hair_group] = int(bucket["hair"].get(hair_group, 0)) + 1
        if eye_group:
            bucket["eyes"][eye_group] = int(bucket["eyes"].get(eye_group, 0)) + 1

    profiles: dict[str, _CharacterCorrelationProfile] = {}
    for character_id, value in profile_counts.items():
        hair_groups = frozenset(str(name) for name in value["hair"].keys() if str(name))
        eye_groups = frozenset(str(name) for name in value["eyes"].keys() if str(name))
        profiles[character_id] = _CharacterCorrelationProfile(
            hair_groups=hair_groups,
            eye_groups=eye_groups,
        )
    return profiles


def _get_character_correlation_profiles(
    custom_index: CharacterVectorIndex,
    tag_index: dict[str, int],
) -> dict[str, _CharacterCorrelationProfile]:
    tag_signature = _tag_index_signature(tag_index)
    index_signature = _character_index_signature(custom_index)
    cache_key = f"{tag_signature}:{index_signature}"
    cached_key = getattr(custom_index, "_correlation_profile_cache_key", None)
    cached_profiles = getattr(custom_index, "_correlation_profiles", None)
    if cached_key == cache_key and isinstance(cached_profiles, dict) and cached_profiles:
        return cached_profiles

    profile_path_value = getattr(custom_index, "_correlation_profile_path", None)
    profile_path = Path(profile_path_value) if isinstance(profile_path_value, Path) else None
    if profile_path is not None:
        loaded = _load_correlation_profiles_from_file(
            profile_path=profile_path,
            expected_tag_signature=tag_signature,
            expected_index_signature=index_signature,
        )
        if loaded:
            custom_index._correlation_profile_cache_key = cache_key  # type: ignore[attr-defined]
            custom_index._correlation_profiles = loaded  # type: ignore[attr-defined]
            return loaded

    profiles = _build_character_correlation_profiles(custom_index, tag_index)
    if profile_path is not None and profiles:
        try:
            _save_correlation_profiles_to_file(
                profile_path=profile_path,
                profiles=profiles,
                tag_signature=tag_signature,
                index_signature=index_signature,
            )
        except Exception:
            pass
    custom_index._correlation_profile_cache_key = cache_key  # type: ignore[attr-defined]
    custom_index._correlation_profiles = profiles  # type: ignore[attr-defined]
    return profiles


def rebuild_character_correlation_profiles(
    custom_index: CharacterVectorIndex,
    tag_index: dict[str, int],
) -> dict[str, _CharacterCorrelationProfile]:
    """Force rebuild and persist character correlation profiles."""
    tag_signature = _tag_index_signature(tag_index)
    index_signature = _character_index_signature(custom_index)
    cache_key = f"{tag_signature}:{index_signature}"
    profiles = _build_character_correlation_profiles(custom_index, tag_index)

    profile_path_value = getattr(custom_index, "_correlation_profile_path", None)
    profile_path = Path(profile_path_value) if isinstance(profile_path_value, Path) else None
    if profile_path is not None and profiles:
        try:
            _save_correlation_profiles_to_file(
                profile_path=profile_path,
                profiles=profiles,
                tag_signature=tag_signature,
                index_signature=index_signature,
            )
        except Exception:
            pass
    custom_index._correlation_profile_cache_key = cache_key  # type: ignore[attr-defined]
    custom_index._correlation_profiles = profiles  # type: ignore[attr-defined]
    return profiles


def _correlation_multiplier(
    hair_group: str,
    hair_score: float,
    eye_group: str,
    eye_score: float,
    profile: _CharacterCorrelationProfile | None,
) -> float:
    if profile is None:
        return 1.0
    factor = 1.0
    hair_mismatch = False
    eye_mismatch = False

    if hair_group and float(hair_score) >= CORRELATION_QUERY_MIN_HAIR_SCORE and profile.hair_groups:
        if hair_group in profile.hair_groups or "multi" in profile.hair_groups:
            factor *= 1.05
        else:
            factor *= 0.88
            hair_mismatch = True

    if eye_group and float(eye_score) >= CORRELATION_QUERY_MIN_EYE_SCORE and profile.eye_groups:
        if eye_group in profile.eye_groups or "multi" in profile.eye_groups:
            factor *= 1.03
        else:
            factor *= 0.92
            eye_mismatch = True

    if hair_mismatch and eye_mismatch:
        factor *= 0.90
    return float(max(0.70, min(1.18, factor)))


def _head_candidate_score(predicted_tags: Iterable[ModelTag]) -> float:
    score_by_name: dict[str, float] = {}
    for tag in predicted_tags:
        if str(tag.category).strip() != "general":
            continue
        score_by_name[normalize_token(tag.name)] = float(tag.score)

    score = 0.0
    for name, weight in HEAD_SIGNAL_TAG_WEIGHTS.items():
        score += weight * float(score_by_name.get(name, 0.0))
    for name, weight in HEAD_NEGATIVE_TAG_WEIGHTS.items():
        score += weight * float(score_by_name.get(name, 0.0))
    return max(0.0, float(score))


def _build_split_head_ratio_boxes(inferred_count: int) -> list[tuple[float, float, float, float]]:
    count = max(1, min(int(inferred_count), MAX_HEAD_QUERY_REGIONS))
    if count <= 1:
        return []

    boxes: list[tuple[float, float, float, float]] = []
    step = 1.0 / float(count)
    lane_width = min(0.50, max(0.28, step * 0.95))
    half = lane_width / 2.0
    for index in range(count):
        center = (index + 0.5) * step
        left = max(0.0, center - half)
        right = min(1.0, center + half)
        boxes.append((left, 0.00, right, 0.56))
        boxes.append((left, 0.08, right, 0.66))
    return boxes


def _build_probe_head_ratio_boxes() -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    for center in HEAD_PROBE_CENTERS:
        for half_width in HEAD_PROBE_HALF_WIDTHS:
            left = max(0.0, center - half_width)
            right = min(1.0, center + half_width)
            if right - left <= 0.0:
                continue
            for top, bottom in HEAD_PROBE_VERTICAL_RANGES:
                boxes.append((left, top, right, bottom))
    return boxes


def _generate_head_candidate_boxes(
    width: int,
    height: int,
    inferred_count: int,
) -> list[tuple[int, int, int, int]]:
    ratio_specs = _build_split_head_ratio_boxes(inferred_count)
    ratio_specs.extend(list(HEAD_BASE_REGION_SPECS))
    ratio_specs.extend(_build_probe_head_ratio_boxes())
    boxes: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for left_ratio, top_ratio, right_ratio, bottom_ratio in ratio_specs:
        box = _normalized_crop_box(
            width=width,
            height=height,
            left_ratio=left_ratio,
            top_ratio=top_ratio,
            right_ratio=right_ratio,
            bottom_ratio=bottom_ratio,
        )
        if box is None or box in seen:
            continue
        seen.add(box)
        boxes.append(box)
    return boxes


def _select_head_regions(
    image: Image.Image,
    tagger: WD14Tagger,
    inferred_count: int,
) -> list[tuple[np.ndarray, float]]:
    width, height = image.size
    raw_boxes = _generate_head_candidate_boxes(width=width, height=height, inferred_count=inferred_count)
    if not raw_boxes:
        return []
    candidate_eval_limit = (
        MAX_HEAD_CANDIDATE_EVAL_MULTI if int(inferred_count) > 1 else MAX_HEAD_CANDIDATE_EVAL_SINGLE
    )
    candidate_eval_limit = max(1, int(candidate_eval_limit))
    target_count = max(1, min(int(inferred_count), MAX_HEAD_QUERY_REGIONS))
    scored: list[tuple[float, float, float, tuple[int, int, int, int], np.ndarray]] = []

    def _append_scored(boxes: Iterable[tuple[int, int, int, int]]) -> None:
        for box in boxes:
            crop = image.crop(box)
            try:
                predicted, vector = tagger.predict_with_vector_from_image(crop)
            except Exception:
                continue
            head_score = _head_candidate_score(predicted)
            width_box = max(1, box[2] - box[0])
            height_box = max(1, box[3] - box[1])
            area_ratio = float(width_box * height_box) / float(max(1, width * height))
            effective_head_score = head_score - max(0.0, area_ratio - 0.18) * 0.60
            scored.append(
                (
                    float(effective_head_score),
                    float(head_score),
                    area_ratio,
                    box,
                    np.asarray(vector, dtype=np.float32).reshape(-1),
                )
            )

    def _select_from_scored() -> list[tuple[float, float, float, tuple[int, int, int, int], np.ndarray]]:
        if not scored:
            return []
        ranked = sorted(scored, key=lambda item: (item[0], -item[2]), reverse=True)
        selected_local: list[tuple[float, float, float, tuple[int, int, int, int], np.ndarray]] = []
        for candidate in ranked:
            _effective_head_score, head_score, _area_ratio, box, vector = candidate
            if any(
                _box_iou(box, existing_box) >= HEAD_NMS_IOU_THRESHOLD
                for _, _, _, existing_box, _ in selected_local
            ):
                continue
            if any(
                _cosine_similarity(vector, existing_vector) >= HEAD_VECTOR_DUPLICATE_SIMILARITY
                for _, _, _, _, existing_vector in selected_local
            ):
                continue
            if head_score < HEAD_SCORE_MIN_THRESHOLD and len(selected_local) >= target_count:
                continue
            selected_local.append(candidate)
            if len(selected_local) >= target_count:
                break
        return selected_local

    _append_scored(raw_boxes[:candidate_eval_limit])
    selected = _select_from_scored()

    best_head_score = float(selected[0][1]) if selected else 0.0
    need_fallback = len(selected) < target_count or best_head_score < float(HEAD_FALLBACK_TRIGGER_SCORE)
    if need_fallback and len(raw_boxes) > candidate_eval_limit:
        fallback_eval = (
            HEAD_CANDIDATE_FALLBACK_EVAL_MULTI
            if int(inferred_count) > 1
            else HEAD_CANDIDATE_FALLBACK_EVAL_SINGLE
        )
        fallback_eval = max(0, int(fallback_eval))
        if fallback_eval > 0:
            tail_end = min(len(raw_boxes), candidate_eval_limit + fallback_eval)
            _append_scored(raw_boxes[candidate_eval_limit:tail_end])
            selected = _select_from_scored()

    result: list[tuple[np.ndarray, float]] = []
    for _effective_head_score, head_score, _area_ratio, _box, vector in selected:
        weight = 0.95 + min(0.30, max(0.0, float(head_score)))
        result.append((vector, float(weight)))
    return result


def build_custom_character_query_items(
    image_path: Path,
    full_query_vector: np.ndarray,
    tagger: WD14Tagger,
    inferred_character_count: int = 1,
) -> list[tuple[np.ndarray, float]]:
    """Build weighted query vectors for custom-character retrieval.

    Uses full-image vector as fallback and detected head regions as primary
    queries so facial/hair cues dominate character matching.
    """
    items: list[tuple[np.ndarray, float]] = [
        (np.asarray(full_query_vector, dtype=np.float32).reshape(-1), float(FULL_IMAGE_CHARACTER_WEIGHT))
    ]

    try:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            items.extend(
                _select_head_regions(
                    image=image,
                    tagger=tagger,
                    inferred_count=max(1, int(inferred_character_count)),
                )
            )
    except Exception:
        return items

    if len(items) <= 1:
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                width, height = image.size
                for _name, (left_ratio, top_ratio, right_ratio, bottom_ratio), weight in CHARACTER_REGION_SPECS:
                    box = _normalized_crop_box(
                        width=width,
                        height=height,
                        left_ratio=left_ratio,
                        top_ratio=top_ratio,
                        right_ratio=right_ratio,
                        bottom_ratio=bottom_ratio,
                    )
                    if box is None:
                        continue
                    crop = image.crop(box)
                    try:
                        _, vector = tagger.predict_with_vector_from_image(crop)
                    except Exception:
                        continue
                    items.append((np.asarray(vector, dtype=np.float32).reshape(-1), float(weight)))
        except Exception:
            return items

    return items


@dataclass
class _CharacterEvidence:
    character_id: str
    character_name: str
    best_score: float = 0.0
    best_head_score: float = 0.0
    best_head_region: int = -1
    region_scores: dict[int, float] = field(default_factory=dict)
    reference_rows: set[int] = field(default_factory=set)


def resolve_custom_characters_with_region_queries(
    query_items: Iterable[tuple[np.ndarray, float]],
    custom_index: CharacterVectorIndex | None,
    min_similarity: float,
    top_k: int = 1,
    min_margin: float = 0.0,
    tag_index: dict[str, int] | None = None,
) -> list[str]:
    """Resolve custom characters using weighted multi-region queries."""
    if custom_index is None:
        return []
    query_item_list = list(query_items)
    if not query_item_list:
        return []

    safe_top_k = max(1, int(top_k))
    head_query_count = max(0, len(query_item_list) - 1)
    normalized_tag_index: dict[str, int] = {}
    if tag_index:
        for raw_name, raw_index in tag_index.items():
            normalized_name = normalize_token(str(raw_name))
            if not normalized_name:
                continue
            try:
                normalized_tag_index[normalized_name] = int(raw_index)
            except Exception:
                continue
    correlation_profiles: dict[str, _CharacterCorrelationProfile] = {}
    if normalized_tag_index:
        correlation_profiles = _get_character_correlation_profiles(custom_index, normalized_tag_index)

    reference_count_by_id = getattr(custom_index, "reference_count_by_id", {})
    evidence_by_id: dict[str, _CharacterEvidence] = {}

    for query_index, (query_vector, weight) in enumerate(query_item_list):
        query_array = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        query_weight = max(0.0, float(weight))
        if query_weight <= 0.0:
            continue
        query_hair_group = ""
        query_hair_score = 0.0
        query_eye_group = ""
        query_eye_score = 0.0
        if normalized_tag_index:
            query_hair_group, query_hair_score = _extract_dominant_group(
                vector=query_array,
                tag_index=normalized_tag_index,
                candidates=ATTRIBUTE_HAIR_COLOR_TAGS,
                group_map=HAIR_COLOR_GROUP_MAP,
                min_score=CORRELATION_PROFILE_MIN_SCORE,
            )
            query_eye_group, query_eye_score = _extract_dominant_group(
                vector=query_array,
                tag_index=normalized_tag_index,
                candidates=ATTRIBUTE_EYE_COLOR_TAGS,
                group_map=EYE_COLOR_GROUP_MAP,
                min_score=CORRELATION_PROFILE_MIN_SCORE,
            )
        candidate_limit = max(MIN_CHARACTER_MATCH_CANDIDATES, safe_top_k * 64)
        if custom_index.embeddings.ndim == 2:
            candidate_limit = min(candidate_limit, int(custom_index.embeddings.shape[0]))
        matches = custom_index.query_many(
            query_vector=query_array,
            min_similarity=0.0,
            top_k=candidate_limit,
        )
        for match in matches:
            name = str(match.character_name).strip()
            if not name:
                continue
            character_id = str(match.character_id).strip()
            if not character_id:
                continue
            adjusted_similarity = float(match.similarity)
            profile = correlation_profiles.get(character_id)
            adjusted_similarity *= _correlation_multiplier(
                hair_group=query_hair_group,
                hair_score=query_hair_score,
                eye_group=query_eye_group,
                eye_score=query_eye_score,
                profile=profile,
            )
            if normalized_tag_index:
                row_index = int(match.row_index)
                if 0 <= row_index < custom_index.embeddings.shape[0]:
                    reference_vector = np.asarray(custom_index.embeddings[row_index], dtype=np.float32).reshape(-1)
                    adjustment = _attribute_score_adjustment(
                        query_vector=query_array,
                        reference_vector=reference_vector,
                        tag_index=normalized_tag_index,
                    )
                    if query_weight <= (FULL_IMAGE_CHARACTER_WEIGHT + 0.05):
                        adjustment *= 0.40
                    elif query_weight < 0.90:
                        adjustment *= 0.70
                    adjusted_similarity += adjustment
            adjusted_similarity = max(0.0, min(1.0, adjusted_similarity))
            if adjusted_similarity <= 0.0:
                continue
            score = adjusted_similarity * query_weight
            evidence = evidence_by_id.get(character_id)
            if evidence is None:
                evidence = _CharacterEvidence(character_id=character_id, character_name=name)
                evidence_by_id[character_id] = evidence
            evidence.character_name = name
            if score > evidence.best_score:
                evidence.best_score = score
            if query_index > 0 and score > evidence.best_head_score:
                evidence.best_head_score = score
                evidence.best_head_region = int(query_index)
            previous_region_score = evidence.region_scores.get(query_index)
            if previous_region_score is None or score > previous_region_score:
                evidence.region_scores[query_index] = score
            evidence.reference_rows.add(int(match.row_index))

    if not evidence_by_id:
        return []

    ranked_records: list[tuple[str, str, float, int, float]] = []
    similarity_floor = max(0.0, float(min_similarity))
    for character_id, evidence in evidence_by_id.items():
        final_score = float(evidence.best_score)
        supported_regions = sum(
            1
            for region_index, region_score in evidence.region_scores.items()
            if region_index > 0 and float(region_score) >= (similarity_floor * 0.92)
        )
        if supported_regions >= 2:
            final_score += 0.03 * min(2, supported_regions - 1)
        if len(evidence.reference_rows) >= 2:
            final_score += 0.012 * min(3, len(evidence.reference_rows) - 1)

        reference_count = int(reference_count_by_id.get(character_id, 1))
        if safe_top_k > 1 and head_query_count >= 2 and reference_count <= 1 and evidence.best_head_score < 0.62:
            final_score *= float(SINGLE_REFERENCE_MULTI_SCORE_FACTOR)

        ranked_records.append(
            (
                character_id,
                evidence.character_name,
                final_score,
                evidence.best_head_region,
                evidence.best_head_score,
            )
        )

    ranked = sorted(ranked_records, key=lambda item: item[2], reverse=True)
    best_score = float(ranked[0][2])
    if best_score < float(min_similarity):
        return []
    if safe_top_k <= 1 and len(ranked) >= 2:
        second_score = float(ranked[1][2])
        if (best_score - second_score) < float(min_margin):
            return []
    required_score = float(min_similarity)
    if safe_top_k > 1:
        secondary_ratio = float(MULTI_CHARACTER_SECONDARY_SCORE_RATIO)
        library_rows = int(custom_index.embeddings.shape[0]) if custom_index.embeddings.ndim == 2 else 0
        if library_rows >= HUGE_CHARACTER_LIBRARY_ROWS:
            secondary_ratio += float(HUGE_LIBRARY_SECONDARY_RATIO_DELTA)
        elif library_rows >= LARGE_CHARACTER_LIBRARY_ROWS:
            secondary_ratio += float(LARGE_LIBRARY_SECONDARY_RATIO_DELTA)
        required_score = max(required_score, best_score * secondary_ratio)
    candidates = [item for item in ranked if float(item[2]) >= required_score]
    if safe_top_k <= 1:
        return [candidates[0][1]] if candidates else []

    selected: list[tuple[str, str, float, int, float]] = []
    used_head_regions: set[int] = set()
    for character_id, character_name, score, head_region, head_score in candidates:
        _ = character_id
        if len(selected) >= safe_top_k:
            break
        if not selected:
            selected.append((character_id, character_name, score, head_region, head_score))
            if head_region > 0:
                used_head_regions.add(head_region)
            continue
        if head_region > 0 and head_region in used_head_regions:
            if float(head_score) < (best_score * float(MULTI_CHARACTER_REGION_REUSE_MAX_SCORE_RATIO)):
                continue
        selected.append((character_id, character_name, score, head_region, head_score))
        if head_region > 0:
            used_head_regions.add(head_region)
    return [item[1] for item in selected[:safe_top_k]]


def resolve_custom_characters(
    query_vector: np.ndarray,
    custom_index: CharacterVectorIndex | None,
    min_similarity: float,
    top_k: int = 1,
    min_margin: float = 0.0,
    tag_index: dict[str, int] | None = None,
) -> list[str]:
    """Resolve custom character names using vector retrieval."""
    return resolve_custom_characters_with_region_queries(
        query_items=[(query_vector, 1.0)],
        custom_index=custom_index,
        min_similarity=min_similarity,
        top_k=top_k,
        min_margin=min_margin,
        tag_index=tag_index,
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
    parser.add_argument(
        "--multi-character-threshold-floor",
        type=float,
        default=DEFAULT_MULTI_CHARACTER_THRESHOLD_FLOOR,
        help="Lower-bound threshold used when multiple characters are inferred.",
    )
    parser.add_argument(
        "--rebuild-custom-index",
        action="store_true",
        help="Force rebuild custom character index instead of using cached index.npz.",
    )
    parser.add_argument(
        "--rebuild-correlation-profiles",
        action="store_true",
        help="Force rebuild cached custom correlation_profiles.json before matching.",
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
    wd14_tag_index = {
        normalize_token(name): index for index, (name, _category) in enumerate(tagger.tags)
    }
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
    custom_index = load_or_build_custom_character_index(
        store=custom_store,
        tagger=tagger,
        preferred_language=str(args.custom_character_language).strip() or "zh-CN",
        rebuild=bool(args.rebuild_custom_index),
    )
    if custom_index is not None and bool(args.rebuild_correlation_profiles):
        rebuild_character_correlation_profiles(custom_index, wd14_tag_index)

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
        inferred_character_count = infer_character_count(predicted, min_score=0.35, max_count=3)
        character_query_items = build_custom_character_query_items(
            image_path=image_path,
            full_query_vector=score_vector,
            tagger=tagger,
            inferred_character_count=inferred_character_count,
        )
        detected_head_count = max(0, len(character_query_items) - 1)
        effective_character_top_k = resolve_effective_character_top_k(
            base_top_k=int(args.custom_character_topk),
            inferred_count=inferred_character_count,
            detected_head_count=detected_head_count,
        )
        effective_character_threshold = resolve_effective_character_threshold(
            base_threshold=args.custom_character_threshold,
            inferred_count=inferred_character_count,
            multi_floor=args.multi_character_threshold_floor,
        )
        characters = resolve_custom_characters_with_region_queries(
            query_items=character_query_items,
            custom_index=custom_index,
            min_similarity=effective_character_threshold,
            top_k=effective_character_top_k,
            min_margin=max(0.0, float(args.custom_character_margin)),
            tag_index=wd14_tag_index,
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
