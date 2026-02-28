"""Identity-aware candidate filtering for bulk reference augmentation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import numpy as np
import requests
from PIL import Image

try:
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional runtime availability
    ort = None


LOGGER = logging.getLogger("moegirl.reference_identity")
CLIP_VISION_MODEL_URL = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/vision_model.onnx"
CLIP_VISION_MODEL_NAME = "vision_model.onnx"
CLIP_INPUT_SIZE = 224
CLIP_MEAN = np.asarray([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.asarray([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


class ImageEmbedder(Protocol):
    def encode_image(self, image_path: Path) -> np.ndarray | None:
        """Encode one image into a normalized embedding vector."""


def _normalize_vector(vector: np.ndarray) -> np.ndarray | None:
    raw = np.asarray(vector, dtype=np.float32).reshape(-1)
    if raw.size == 0:
        return None
    norm = float(np.linalg.norm(raw))
    if norm <= 0.0:
        return None
    return (raw / norm).astype(np.float32)


class ClipOnnxImageEmbedder:
    """Compute CLIP image embeddings with ONNXRuntime (CPU)."""

    def __init__(
        self,
        model_dir: Path,
        model_url: str = CLIP_VISION_MODEL_URL,
        http_client: requests.Session | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / CLIP_VISION_MODEL_NAME
        self.model_url = str(model_url).strip() or CLIP_VISION_MODEL_URL
        self.http_client = http_client if http_client is not None else requests.Session()
        self._session = None
        self._input_name = "pixel_values"
        self._output_name = "image_embeds"

    def _ensure_model_file(self) -> bool:
        if self.model_path.exists() and self.model_path.is_file() and self.model_path.stat().st_size > 1_000_000:
            return True
        self.model_dir.mkdir(parents=True, exist_ok=True)
        try:
            with self.http_client.get(self.model_url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with self.model_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
        except Exception as error:
            LOGGER.warning("clip model download failed url=%s error=%s", self.model_url, error)
            return False
        return self.model_path.exists() and self.model_path.is_file()

    def _ensure_session(self) -> bool:
        if self._session is not None:
            return True
        if ort is None:
            LOGGER.warning("onnxruntime unavailable; identity filtering disabled")
            return False
        if not self._ensure_model_file():
            return False
        try:
            session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        except Exception as error:
            LOGGER.warning("clip model load failed path=%s error=%s", self.model_path, error)
            return False
        self._session = session
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if inputs:
            self._input_name = str(inputs[0].name)
        if outputs:
            self._output_name = str(outputs[0].name)
        return True

    @staticmethod
    def _prepare_input(image_path: Path) -> np.ndarray | None:
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                width, height = image.size
                if width <= 0 or height <= 0:
                    return None
                scale = CLIP_INPUT_SIZE / float(min(width, height))
                resized = image.resize(
                    (
                        max(CLIP_INPUT_SIZE, int(round(width * scale))),
                        max(CLIP_INPUT_SIZE, int(round(height * scale))),
                    ),
                    Image.Resampling.BICUBIC,
                )
                resized_width, resized_height = resized.size
                left = max(0, (resized_width - CLIP_INPUT_SIZE) // 2)
                top = max(0, (resized_height - CLIP_INPUT_SIZE) // 2)
                crop = resized.crop((left, top, left + CLIP_INPUT_SIZE, top + CLIP_INPUT_SIZE))
        except Exception:
            return None
        tensor = np.asarray(crop, dtype=np.float32) / 255.0
        tensor = (tensor - CLIP_MEAN) / CLIP_STD
        tensor = np.transpose(tensor, (2, 0, 1))
        return np.expand_dims(tensor.astype(np.float32), axis=0)

    def encode_image(self, image_path: Path) -> np.ndarray | None:
        if not self._ensure_session():
            return None
        tensor = self._prepare_input(Path(image_path))
        if tensor is None:
            return None
        try:
            outputs = self._session.run([self._output_name], {self._input_name: tensor})
        except Exception as error:
            LOGGER.info("clip encode failed path=%s error=%s", image_path, error)
            return None
        if not outputs:
            return None
        return _normalize_vector(np.asarray(outputs[0], dtype=np.float32))


class ReferenceIdentityFilter:
    """Filter downloaded candidates using CLIP image-image similarity."""

    def __init__(
        self,
        embedder: ImageEmbedder | None = None,
        model_dir: Path | None = None,
        similarity_threshold: float = 0.45,
        min_side: int = 96,
        max_seed_images: int = 8,
        avatar_seed_threshold: float = 0.50,
        avatar_candidate_threshold: float = 0.52,
        avatar_top_band_margin: float = 0.10,
    ) -> None:
        self.embedder = embedder if embedder is not None else ClipOnnxImageEmbedder(model_dir=model_dir or Path("tools/clip-vit-b32"))
        self.similarity_threshold = float(similarity_threshold)
        self.min_side = max(1, int(min_side))
        self.max_seed_images = max(1, int(max_seed_images))
        self.avatar_seed_threshold = float(avatar_seed_threshold)
        self.avatar_candidate_threshold = float(avatar_candidate_threshold)
        self.avatar_top_band_margin = max(0.0, float(avatar_top_band_margin))

    def _collect_seed_paths(self, record: dict, custom_root: Path) -> list[Path]:
        candidates: list[Path] = []
        avatar_relative = str(record.get("avatar_local_path", "")).strip()
        if avatar_relative:
            candidates.append((custom_root / Path(avatar_relative)).resolve())
        for value in record.get("reference_images", []):
            relative = str(value).strip()
            if not relative:
                continue
            candidates.append((custom_root / Path(relative)).resolve())

        unique: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = path.as_posix()
            if key in seen:
                continue
            seen.add(key)
            if path.exists() and path.is_file():
                unique.append(path)
            if len(unique) >= self.max_seed_images:
                break
        return unique

    def _meets_image_size(self, path: Path) -> bool:
        try:
            with Image.open(path) as source:
                width, height = source.size
        except Exception:
            return False
        return int(width) >= self.min_side and int(height) >= self.min_side

    def select_candidates(
        self,
        *,
        record: dict,
        custom_root: Path,
        candidate_paths: list[Path],
        limit: int,
    ) -> tuple[list[Path], dict]:
        safe_limit = max(1, int(limit))
        normalized_candidates = [Path(path).resolve() for path in candidate_paths if Path(path).exists() and Path(path).is_file()]
        if not normalized_candidates:
            return [], {"mode": "empty", "candidate_count": 0, "kept_count": 0, "seed_count": 0}

        root = Path(custom_root).resolve()
        avatar_relative = str(record.get("avatar_local_path", "")).strip()
        avatar_path = (root / Path(avatar_relative)).resolve() if avatar_relative else None
        has_avatar = bool(avatar_path and avatar_path.exists() and avatar_path.is_file())

        seed_paths = self._collect_seed_paths(record, root)
        if not seed_paths:
            return normalized_candidates[:safe_limit], {
                "mode": "passthrough_no_seed",
                "candidate_count": len(normalized_candidates),
                "kept_count": min(len(normalized_candidates), safe_limit),
                "seed_count": 0,
            }

        seed_vectors_by_path: dict[Path, np.ndarray] = {}
        for seed_path in seed_paths:
            vector = self.embedder.encode_image(seed_path)
            vector = _normalize_vector(vector) if vector is not None else None
            if vector is None:
                continue
            seed_vectors_by_path[seed_path] = vector
        if not seed_vectors_by_path:
            if has_avatar:
                return [], {
                    "mode": "reject_no_seed_vector",
                    "candidate_count": len(normalized_candidates),
                    "kept_count": 0,
                    "seed_count": 0,
                }
            return normalized_candidates[:safe_limit], {
                "mode": "passthrough_no_seed_vector",
                "candidate_count": len(normalized_candidates),
                "kept_count": min(len(normalized_candidates), safe_limit),
                "seed_count": 0,
            }

        seed_vectors: list[np.ndarray] = []
        avatar_vector = seed_vectors_by_path.get(avatar_path) if avatar_path is not None else None
        for seed_path, vector in seed_vectors_by_path.items():
            if avatar_vector is not None and seed_path != avatar_path:
                similarity_to_avatar = float(np.dot(vector, avatar_vector))
                if similarity_to_avatar < self.avatar_seed_threshold:
                    continue
            seed_vectors.append(vector)
        if not seed_vectors:
            return [], {
                "mode": "reject_no_clean_seed_vector",
                "candidate_count": len(normalized_candidates),
                "kept_count": 0,
                "seed_count": 0,
            }

        centroid = _normalize_vector(np.mean(np.stack(seed_vectors).astype(np.float32), axis=0))
        if centroid is None:
            return [], {
                "mode": "reject_invalid_seed_center",
                "candidate_count": len(normalized_candidates),
                "kept_count": 0,
                "seed_count": len(seed_vectors),
            }

        scored: list[tuple[float, float, float, Path]] = []
        for candidate_path in normalized_candidates:
            if not self._meets_image_size(candidate_path):
                continue
            vector = self.embedder.encode_image(candidate_path)
            vector = _normalize_vector(vector) if vector is not None else None
            if vector is None:
                continue
            similarity_centroid = float(np.dot(vector, centroid))
            similarity_avatar = float(np.dot(vector, avatar_vector)) if avatar_vector is not None else similarity_centroid
            weighted_score = 0.65 * similarity_centroid + 0.35 * similarity_avatar
            scored.append((weighted_score, similarity_centroid, similarity_avatar, candidate_path))
        scored.sort(key=lambda item: item[0], reverse=True)

        if not scored:
            return [], {
                "mode": "reject_no_candidate_vector",
                "candidate_count": len(normalized_candidates),
                "kept_count": 0,
                "seed_count": len(seed_vectors),
            }

        best_avatar = max(item[2] for item in scored) if scored else 0.0
        avatar_dynamic_floor = max(self.avatar_candidate_threshold, float(best_avatar) - self.avatar_top_band_margin)
        filtered = []
        for _weighted, sim_centroid, sim_avatar, path in scored:
            if sim_centroid < self.similarity_threshold:
                continue
            if avatar_vector is not None and sim_avatar < avatar_dynamic_floor:
                continue
            filtered.append(path)
        mode = "filtered" if filtered else "reject_low_confidence"
        if filtered:
            kept = filtered[:safe_limit]
        else:
            kept = []

        kept_scores = [score for score, _sim_centroid, _sim_avatar, path in scored if path in set(kept)]
        return kept, {
            "mode": mode,
            "candidate_count": len(normalized_candidates),
            "scored_count": len(scored),
            "kept_count": len(kept),
            "seed_count": len(seed_vectors),
            "threshold": self.similarity_threshold,
            "avatar_threshold": self.avatar_candidate_threshold,
            "avatar_dynamic_floor": avatar_dynamic_floor if avatar_vector is not None else 0.0,
            "best_similarity": float(scored[0][0]),
            "worst_kept_similarity": float(min(kept_scores)) if kept_scores else 0.0,
        }
