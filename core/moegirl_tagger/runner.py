"""Run auto-tagging pipeline as a reusable shared service."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AutoTagOptions:
    """Options for auto-tagging execution."""

    image_dir: str = "image"
    queue_output: str = "data/annotation_queue/pending_annotations.jsonl"
    taxonomy: str = "data/character_library/feature_taxonomy.json"
    synonyms: str = "data/character_library/feature_synonyms.json"
    priority_rules: str = "data/character_library/feature_priority_rules.json"
    model_dir: str = "tools/wd14"
    exiftool_dir: str = "tools/exiftool"
    input_list: str = ""
    feature_threshold: float = 0.62
    adult_feature_threshold: float = 0.55
    footwear_feature_threshold: float = 0.50
    barefoot_feature_threshold: float = 0.35
    copyright_threshold: float = 0.70
    custom_character_language: str = "zh-CN"
    onnx_provider: str = "auto"
    recognize_characters: bool = True


def parse_pipeline_summary(stdout: str) -> dict[str, int]:
    """Parse numeric summary from auto-tag stdout.

    Args:
        stdout: Command stdout text.

    Returns:
        Summary fields.
    """
    mapping = {
        "Images found": "images_found",
        "Queue written": "queue_written",
        "Metadata targets": "metadata_targets",
        "Metadata updated": "metadata_updated",
        "Metadata skipped": "metadata_skipped",
    }
    result = {
        "images_found": 0,
        "queue_written": 0,
        "metadata_targets": 0,
        "metadata_updated": 0,
        "metadata_skipped": 0,
    }
    for line in stdout.splitlines():
        text = line.strip()
        for raw_key, key in mapping.items():
            if text.startswith(f"{raw_key}:"):
                match = re.search(r"(\d+)", text)
                if match:
                    result[key] = int(match.group(1))
    return result


def build_auto_tag_command(
    options: AutoTagOptions,
    script_path: Path,
) -> list[str]:
    """Build command for scripts/auto_tag_images.py.

    Args:
        options: Runtime options.
        script_path: Script path.

    Returns:
        Shell-safe argument list.
    """
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(script_path),
        "--image-dir",
        options.image_dir,
        "--queue-output",
        options.queue_output,
        "--taxonomy",
        options.taxonomy,
        "--synonyms",
        options.synonyms,
        "--priority-rules",
        options.priority_rules,
        "--model-dir",
        options.model_dir,
        "--exiftool-dir",
        options.exiftool_dir,
        "--feature-threshold",
        str(options.feature_threshold),
        "--adult-feature-threshold",
        str(options.adult_feature_threshold),
        "--footwear-feature-threshold",
        str(options.footwear_feature_threshold),
        "--barefoot-feature-threshold",
        str(options.barefoot_feature_threshold),
        "--copyright-threshold",
        str(options.copyright_threshold),
        "--custom-character-language",
        options.custom_character_language,
        "--onnx-provider",
        options.onnx_provider,
    ]
    if not options.recognize_characters:
        command.append("--disable-character-recognition")
    if options.input_list:
        command.extend(["--input-list", options.input_list])
    return command


def run_auto_tag_pipeline(
    options: AutoTagOptions | None = None,
    project_root: Path | None = None,
) -> dict[str, object]:
    """Execute auto-tag script and return summary.

    Args:
        options: Optional run options.
        project_root: Repository root path.

    Returns:
        Result with command, summary and outputs.

    Raises:
        RuntimeError: If script execution fails.
    """
    resolved_options = options if options else AutoTagOptions()
    root = project_root.resolve() if project_root else Path.cwd().resolve()
    script_path = root / "scripts" / "auto_tag_images.py"
    command = build_auto_tag_command(resolved_options, script_path)

    process = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    summary = parse_pipeline_summary(process.stdout)
    if process.returncode != 0:
        raise RuntimeError(
            "自动打标执行失败。\n"
            f"命令: {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\n"
            f"stderr:\n{process.stderr}"
        )

    return {
        "command": command,
        "summary": summary,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
