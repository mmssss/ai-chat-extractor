"""
Source-adapter registry: a frozen dataclass per supported AI assistant,
plus a ``get_source`` helper to look one up by name.

Adding a third source (e.g. Gemini) is a matter of writing `<name>_parsers.py`
and `<name>_metadata.py` with the same public surface, then registering a
new `SourceAdapter` entry in `SOURCES`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Dict, List

try:
    from . import codex_metadata, codex_parsers, metadata, parsers
except ImportError:
    import codex_metadata
    import codex_parsers
    import metadata
    import parsers


@dataclass(frozen=True)
class SourceAdapter:
    """Per-source configuration + references to the right parser modules."""

    name: str
    display_name: str
    filename_prefix: str
    default_source_dir: Path
    output_dir_suggestions: List[Path]
    cache_subdir: Path
    parsers: ModuleType
    metadata: ModuleType


SOURCES: Dict[str, SourceAdapter] = {
    "claude": SourceAdapter(
        name="claude",
        display_name="Claude",
        filename_prefix="claude",
        default_source_dir=Path.home() / ".claude" / "projects",
        output_dir_suggestions=[
            Path.home() / "Desktop" / "Claude Conversations",
            Path.home() / "Documents" / "Claude Conversations",
            Path.home() / "Downloads" / "Claude Conversations",
            Path.cwd() / "Claude Conversations",
        ],
        cache_subdir=Path.home() / ".claude" / ".search_cache",
        parsers=parsers,
        metadata=metadata,
    ),
    "codex": SourceAdapter(
        name="codex",
        display_name="Codex",
        filename_prefix="codex",
        default_source_dir=Path.home() / ".codex" / "sessions",
        output_dir_suggestions=[
            Path.home() / "Desktop" / "Codex Conversations",
            Path.home() / "Documents" / "Codex Conversations",
            Path.home() / "Downloads" / "Codex Conversations",
            Path.cwd() / "Codex Conversations",
        ],
        cache_subdir=Path.home() / ".codex" / ".search_cache",
        parsers=codex_parsers,
        metadata=codex_metadata,
    ),
}


def get_source(name: str) -> SourceAdapter:
    """Return the SourceAdapter for ``name`` or raise ``ValueError``."""
    try:
        return SOURCES[name]
    except KeyError as exc:
        known = ", ".join(sorted(SOURCES))
        raise ValueError(
            f"Unknown source: {name!r}. Known sources: {known}"
        ) from exc
