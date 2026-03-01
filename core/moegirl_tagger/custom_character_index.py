"""Vector index helpers for runtime custom character retrieval."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class CharacterVectorMatch:
    """Single retrieval match from character vector index."""

    character_id: str
    character_name: str
    image_path: str
    similarity: float
    row_index: int


class CharacterVectorIndex:
    """In-memory cosine-similarity index for character reference embeddings."""

    def __init__(
        self,
        embeddings: np.ndarray,
        character_ids: list[str],
        character_names: list[str],
        image_paths: list[str],
    ) -> None:
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = np.expand_dims(matrix, axis=0)

        count = matrix.shape[0] if matrix.size else 0
        if count != len(character_ids) or count != len(character_names) or count != len(image_paths):
            raise ValueError("Embedding rows and metadata lengths do not match.")

        self.embeddings = matrix
        self.character_ids = [str(value) for value in character_ids]
        self.character_names = [str(value) for value in character_names]
        self.image_paths = [str(value) for value in image_paths]
        self._normalized = self._normalize_rows(self.embeddings)
        counts: dict[str, int] = {}
        for character_id in self.character_ids:
            counts[character_id] = counts.get(character_id, 0) + 1
        self.reference_count_by_id = counts

    @staticmethod
    def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
        if matrix.size == 0:
            return matrix.astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0.0, 1.0, norms)
        return (matrix / norms).astype(np.float32)

    @property
    def is_empty(self) -> bool:
        return self.embeddings.size == 0 or self.embeddings.shape[0] == 0

    def query_many(
        self,
        query_vector: np.ndarray,
        min_similarity: float = 0.0,
        top_k: int = 1,
    ) -> list[CharacterVectorMatch]:
        if self.is_empty or top_k <= 0:
            return []

        query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query.size != self._normalized.shape[1]:
            return []

        query_norm = float(np.linalg.norm(query))
        if query_norm <= 0.0:
            return []
        query_unit = query / query_norm
        scores = np.dot(self._normalized, query_unit)
        if scores.ndim != 1 or scores.size == 0:
            return []

        order = np.argsort(scores)[::-1]
        matches: list[CharacterVectorMatch] = []
        for index in order[:top_k]:
            similarity = float(scores[index])
            if similarity < min_similarity:
                continue
            matches.append(
                CharacterVectorMatch(
                    character_id=self.character_ids[int(index)],
                    character_name=self.character_names[int(index)],
                    image_path=self.image_paths[int(index)],
                    similarity=similarity,
                    row_index=int(index),
                )
            )
        return matches

    def query(
        self,
        query_vector: np.ndarray,
        min_similarity: float = 0.0,
        top_k: int = 1,
    ) -> CharacterVectorMatch | None:
        matches = self.query_many(query_vector=query_vector, min_similarity=min_similarity, top_k=top_k)
        if not matches:
            return None
        return matches[0]

    def save(
        self,
        index_path: Path,
        meta_path: Path,
        model_type: str = "wd14-score-vector",
    ) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            index_path,
            embeddings=self.embeddings.astype(np.float32),
            character_ids=np.asarray(self.character_ids, dtype=object),
            character_names=np.asarray(self.character_names, dtype=object),
            image_paths=np.asarray(self.image_paths, dtype=object),
        )
        meta = {
            "model_type": model_type,
            "dimension": int(self.embeddings.shape[1]) if self.embeddings.ndim == 2 and self.embeddings.size else 0,
            "record_count": int(self.embeddings.shape[0]) if self.embeddings.ndim == 2 else 0,
            "build_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, index_path: Path, meta_path: Path | None = None) -> "CharacterVectorIndex":
        data = np.load(index_path, allow_pickle=True)
        embeddings = np.asarray(data["embeddings"], dtype=np.float32)
        character_ids = [str(value) for value in data["character_ids"].tolist()]
        character_names = [str(value) for value in data["character_names"].tolist()]
        image_paths = [str(value) for value in data["image_paths"].tolist()]

        if meta_path and meta_path.exists():
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                dimension = int(payload.get("dimension", embeddings.shape[1] if embeddings.ndim == 2 else 0))
                if embeddings.ndim == 2 and embeddings.shape[1] != dimension:
                    raise ValueError("Index dimension mismatch.")
            except Exception:
                # Ignore metadata parse errors and trust NPZ content.
                pass

        return cls(
            embeddings=embeddings,
            character_ids=character_ids,
            character_names=character_names,
            image_paths=image_paths,
        )
