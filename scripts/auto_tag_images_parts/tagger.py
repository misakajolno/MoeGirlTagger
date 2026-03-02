"""Tagger and feature normalization helpers for auto tag image pipeline."""

from __future__ import annotations

import csv
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
    from scripts.auto_tag_images_parts.constants import COPYRIGHT_GAME_MAP, MODEL_URL, TAGS_URL
    from scripts.write_tags_to_image_metadata import (
        load_sensitive_terms_payload,
        load_taxonomy_map,
    )
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.auto_tag_images_parts.constants import COPYRIGHT_GAME_MAP, MODEL_URL, TAGS_URL
    from scripts.write_tags_to_image_metadata import (
        load_sensitive_terms_payload,
        load_taxonomy_map,
    )

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


def resolve_onnx_execution_providers(
    preferred: str = "auto",
    available_providers: list[str] | None = None,
) -> list[str]:
    """Resolve provider order with graceful fallback."""
    normalized = str(preferred or "").strip().lower()
    alias_map = {
        "": "auto",
        "auto": "auto",
        "cpu": "cpu",
        "cuda": "cuda",
        "gpu": "cuda",
        "directml": "directml",
        "dml": "directml",
    }
    mode = alias_map.get(normalized, "auto")
    available = available_providers if available_providers is not None else list(ort.get_available_providers())
    available_set = {str(provider).strip() for provider in available if str(provider).strip()}
    order_by_mode = {
        "auto": ["CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"],
        "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
        "directml": ["DmlExecutionProvider", "CPUExecutionProvider"],
        "cpu": ["CPUExecutionProvider"],
    }

    resolved: list[str] = []
    seen: set[str] = set()
    for provider in order_by_mode[mode]:
        if provider in seen:
            continue
        if provider not in available_set:
            continue
        resolved.append(provider)
        seen.add(provider)

    if not resolved and "CPUExecutionProvider" in available_set:
        resolved.append("CPUExecutionProvider")
    if not resolved:
        for provider in available:
            text = str(provider).strip()
            if text and text not in seen:
                resolved.append(text)
                break
    return resolved


@dataclass
class ModelTag:
    """One model output tag with score and category."""

    name: str
    category: str
    score: float


class WD14Tagger:
    """WD14 ONNX tagger wrapper."""

    def __init__(self, model_path: Path, tags_path: Path, execution_provider: str = "auto") -> None:
        self.model_path = model_path
        self.tags_path = tags_path
        self.tags = self._load_tags(tags_path)
        self._general_tag_last_index_by_normalized_name = self._build_general_tag_last_index(self.tags)
        self.execution_provider = str(execution_provider or "").strip().lower() or "auto"
        provider_order = resolve_onnx_execution_providers(self.execution_provider)
        self._preload_runtime_dlls_for_provider_order(provider_order)
        self.session = ort.InferenceSession(
            str(model_path),
            providers=provider_order,
        )
        self.active_execution_providers = list(self.session.get_providers())
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

    @staticmethod
    def _build_general_tag_last_index(tags: list[tuple[str, str]]) -> dict[str, int]:
        """Build normalized general-tag -> last row index mapping."""
        result: dict[str, int] = {}
        for index, (tag_name, category) in enumerate(tags):
            if str(category).strip() != "general":
                continue
            normalized = normalize_token(tag_name)
            if not normalized:
                continue
            result[normalized] = int(index)
        return result

    @staticmethod
    def _preload_runtime_dlls_for_provider_order(provider_order: list[str]) -> None:
        """Best-effort preload for CUDA EP dependencies on Windows."""
        if "CUDAExecutionProvider" not in provider_order:
            return
        preload = getattr(ort, "preload_dlls", None)
        if not callable(preload):
            return
        # Prefer nvidia site-packages (installed via pip) before default DLL paths.
        try:
            preload(cuda=True, cudnn=True, msvc=True, directory="")
            return
        except Exception:
            pass
        try:
            preload(cuda=True, cudnn=True, msvc=True)
        except Exception:
            pass

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
        scores = np.asarray(score_vector, dtype=np.float32).reshape(-1)
        count = min(int(scores.size), len(self.tags))
        result: list[ModelTag] = []
        for index in range(count):
            tag_name, category = self.tags[index]
            result.append(ModelTag(name=tag_name, category=category, score=float(scores[index])))
        return result

    def predict_score_vector_from_image(self, image: Image.Image) -> np.ndarray:
        """Run model for in-memory image and return raw score vector."""
        return self._predict_scores_from_image(image)

    def score_for_general_tag(self, score_vector: np.ndarray, normalized_tag_name: str) -> float:
        """Return one normalized general-tag score from model vector."""
        name = str(normalized_tag_name).strip()
        if not name:
            return 0.0
        index = self._general_tag_last_index_by_normalized_name.get(name)
        if index is None:
            return 0.0
        vector = np.asarray(score_vector, dtype=np.float32).reshape(-1)
        if index < 0 or index >= int(vector.size):
            return 0.0
        score = float(vector[index])
        if score <= 0.0:
            return 0.0
        return min(1.0, score)

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

