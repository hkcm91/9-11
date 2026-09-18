"""The engine must not know about any particular collection.

This is the automated half of the "search generic engine directories for
hardcoded 9/11-specific strings" check in ``docs/ENGINE_REFACTOR.md``. If a
collection identifier ever reappears under ``src/historical_engine/``, this
fails and the refactor has regressed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1] / "src" / "historical_engine"
COLLECTIONS_DIR = Path(__file__).resolve().parents[1] / "src" / "evidence_collections"

#: Substrings that would mean a collection has leaked into the engine.
FORBIDDEN_PATTERNS = [
    r"september[\s_-]*11",
    r"\b9[/.]11\b",
    r"\bnist\b",
    r"\barchdisk\b",
    r"voices\s+of",
    r"world\s+trade",
    r"pentagon",
    r"internet-archive-understanding",
    r"sonic\s+memorial",
    r"incident\s+action\s+plan",
    r"\bomeka\b",
    r"\barcgis\b",
    r"holocaust",
]


def _engine_files() -> list[Path]:
    return sorted(
        path
        for path in ENGINE_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_engine_has_files_to_check() -> None:
    assert len(_engine_files()) >= 15


@pytest.mark.parametrize("pattern", FORBIDDEN_PATTERNS)
def test_no_collection_specific_strings_in_the_engine(pattern: str) -> None:
    compiled = re.compile(pattern, re.IGNORECASE)
    offenders = [
        f"{path.relative_to(ENGINE_DIR)}:{number}"
        for path in _engine_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if compiled.search(line)
    ]
    assert not offenders, f"collection-specific string {pattern!r} found at: {offenders}"


def test_the_engine_never_imports_a_collection_or_the_legacy_package() -> None:
    bad_import = re.compile(r"^\s*(from|import)\s+(evidence_collections|archive)\b")
    offenders = [
        f"{path.relative_to(ENGINE_DIR)}:{number}: {line.strip()}"
        for path in _engine_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if bad_import.match(line)
    ]
    assert not offenders, f"engine imports outside the engine: {offenders}"


def test_the_only_collection_name_outside_collections_is_the_documented_default() -> None:
    """The transitional CLI default is the single sanctioned exception."""

    compat = (
        Path(__file__).resolve().parents[1] / "src" / "archive" / "collections_compat.py"
    ).read_text(encoding="utf-8")
    assert 'DEFAULT_COLLECTION_ID = "september11"' in compat
    assert "TRANSITIONAL" in compat


def test_a_collection_does_not_import_another_collection() -> None:
    """Collections are siblings; one must not depend on another."""

    offenders: list[str] = []
    for path in sorted(COLLECTIONS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        owner = path.relative_to(COLLECTIONS_DIR).parts[0]
        if owner.endswith(".py"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = re.match(r"^\s*(?:from|import)\s+evidence_collections\.(\w+)", line)
            if match and match.group(1) != owner:
                offenders.append(f"{path.relative_to(COLLECTIONS_DIR)}:{number}: {line.strip()}")
    assert not offenders, f"cross-collection imports: {offenders}"
