"""Identifier helpers.

Identifiers are short, prefixed, URL-safe strings (``proj_4f2a9c1b8e77``).
Prefixed ids make log lines and SQLite rows self-describing, and the limited
length keeps them usable as directory names.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*_[0-9a-f]{8,32}$")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def new_id(prefix: str) -> str:
    """Return a new identifier such as ``proj_1a2b3c4d5e6f``."""
    if not prefix or not prefix.isidentifier():
        raise ValueError(f"Invalid id prefix: {prefix!r}")
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def is_id(value: str, prefix: str | None = None) -> bool:
    pattern = _ID_RE if prefix is None else re.compile(rf"^{re.escape(prefix)}_[0-9a-f]{{8,32}}$")
    return bool(pattern.match(value))


_SLUG_MAX_LENGTH = 48


def slugify(value: str, *, max_length: int = _SLUG_MAX_LENGTH) -> str:
    """Build a filesystem-safe ASCII slug from a display name.

    Chinese titles collapse to an empty stem, so the caller falls back to the
    project id. That keeps directories portable across Windows/macOS/Linux.
    """
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP_RE.sub("-", normalized.lower()).strip("-")
    slug = slug[:max_length].strip("-")
    return slug


def project_dir_name(name: str, project_id: str) -> str:
    """Directory name for a project: ``<slug>-<short id>``."""
    stem = slugify(name)
    return f"{stem}-{project_id.split('_')[-1]}" if stem else project_id


def safe_join(root, *parts: str):
    """Join path *parts* under *root*, refusing to escape it.

    Guards against path traversal when a project or asset name coming from an
    API payload or an imported archive is used to build a filesystem path.
    """
    from pathlib import Path

    base = Path(root).resolve()
    candidate = base.joinpath(*parts).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError(f"Path escapes the sandbox root: {'/'.join(parts)!r}")
    return candidate
