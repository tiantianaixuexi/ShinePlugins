"""Project directory layout (plan §4.2) and filesystem helpers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

#: Sub-directories created for every new project, relative to the project root.
PROJECT_SUBDIRECTORIES: tuple[str, ...] = (
    "novel/outlines",
    "novel/volumes",
    "novel/chapters",
    "novel/drafts",
    "novel/versions",
    "knowledge/characters",
    "knowledge/events",
    "knowledge/locations",
    "knowledge/timelines",
    "knowledge/foreshadows",
    "knowledge/worldbuilding",
    "knowledge/summaries",
    "indexes/vector",
    "indexes/fulltext",
    "indexes/metadata",
    "storyboards/scripts",
    "storyboards/scenes",
    "storyboards/shots",
    "assets/characters",
    "assets/locations",
    "assets/images",
    "assets/videos",
    "assets/audio",
    "assets/subtitles",
    "renders",
    "logs",
    "database",
)

PROJECT_MANIFEST = "project.json"
PROJECT_DB_NAME = "novel.db"
PROJECT_LOCK_NAME = "project.lock"


def ensure_project_layout(root: Path) -> None:
    """Create the standard directory tree for a project."""
    for relative in PROJECT_SUBDIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)


def write_manifest(root: Path, payload: dict) -> Path:
    """Write ``project.json`` — a portable, human-readable mirror of metadata."""
    target = root / PROJECT_MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def read_manifest(root: Path) -> dict | None:
    target = root / PROJECT_MANIFEST
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def project_db_path(root: Path) -> Path:
    return root / "database" / PROJECT_DB_NAME


def is_project_dir(path: Path) -> bool:
    return (path / PROJECT_MANIFEST).exists() or (path / "database" / PROJECT_DB_NAME).exists()


def remove_project_dir(path: Path) -> None:
    """Delete a project directory tree.

    Only ever called with an explicit hard-delete request and a path that is
    inside the configured projects root (validated by the caller).
    """
    if path.exists():
        shutil.rmtree(path)


def disk_usage(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def ensure_within(root: Path, candidate: Path) -> Path:
    """Resolve *candidate* and guarantee it stays inside *root*."""
    base = Path(root).resolve()
    resolved = Path(candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Path escapes the projects root: {candidate}")
    return resolved
