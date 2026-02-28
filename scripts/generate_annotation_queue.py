"""Generate pending annotation JSONL from an image directory."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def normalize_path(path: Path) -> str:
    """Convert a filesystem path to POSIX string.

    Args:
        path: Path object.

    Returns:
        Normalized POSIX path string.
    """
    return path.as_posix()


def collect_image_files(image_dir: Path, recursive: bool = True) -> list[Path]:
    """Collect image files from a directory.

    Args:
        image_dir: Input image root.
        recursive: Whether to scan recursively.

    Returns:
        Sorted image file list.

    Raises:
        FileNotFoundError: If input directory is missing.
    """
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory does not exist: {image_dir}")
    if not image_dir.is_dir():
        raise FileNotFoundError(f"Image directory is not a directory: {image_dir}")

    pattern = "**/*" if recursive else "*"
    files = [
        path
        for path in image_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files, key=lambda item: normalize_path(item))


def file_sha1(path: Path) -> str:
    """Calculate SHA1 of a file.

    Args:
        path: Input file path.

    Returns:
        SHA1 hex digest.
    """
    hasher = hashlib.sha1()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_record(image_path: Path, relative_to: Path, now_iso: str) -> dict:
    """Build a pending annotation record.

    Args:
        image_path: Absolute image path.
        relative_to: Base path for relative image path.
        now_iso: ISO timestamp.

    Returns:
        Pending annotation record.
    """
    relative_path = normalize_path(image_path.relative_to(relative_to))
    return {
        "image_id": file_sha1(image_path),
        "image_path": relative_path,
        "characters": [],
        "feature_tags": [],
        "source_game": [],
        "review_required": False,
        "status": "pending",
        "created_at": now_iso,
    }


def write_jsonl(output_path: Path, records: Iterable[dict]) -> int:
    """Write records to JSONL file.

    Args:
        output_path: Output JSONL path.
        records: Annotation records.

    Returns:
        Number of written records.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate pending annotation queue JSONL.")
    parser.add_argument(
        "--image-dir",
        default="image",
        help="Image root directory.",
    )
    parser.add_argument(
        "--output",
        default="data/annotation_queue/pending_annotations.jsonl",
        help="Output JSONL path.",
    )
    parser.add_argument(
        "--non-recursive",
        action="store_true",
        help="Disable recursive scanning.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    cwd = Path.cwd()
    image_dir = (cwd / args.image_dir).resolve()
    output_path = (cwd / args.output).resolve()
    recursive = not args.non_recursive
    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()

    image_files = collect_image_files(image_dir=image_dir, recursive=recursive)
    records = [build_record(path, relative_to=cwd, now_iso=now_iso) for path in image_files]
    written = write_jsonl(output_path=output_path, records=records)

    print(f"Image directory: {image_dir}")
    print(f"Output file: {output_path}")
    print(f"Records written: {written}")


if __name__ == "__main__":
    main()
