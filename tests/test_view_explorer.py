"""Tests for the Explorer launcher.

The launcher is the first thing a non-technical reviewer touches, and it runs
on a machine where nobody is watching a terminal. Its directory detection and
its "the data is missing" message are therefore worth pinning.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from view_explorer import (  # noqa: E402
    CANDIDATE_DIRS,
    describe_data,
    find_explorer_dir,
    free_port,
    main,
)

BAT = Path(__file__).resolve().parents[1] / "VIEW_EXPLORER.bat"


def _explorer(directory: Path, *, with_data: bool = True, items: int = 3) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text("<html></html>", encoding="utf-8")
    if with_data:
        (directory / "data").mkdir(exist_ok=True)
        (directory / "data" / "explorer.json").write_text(
            json.dumps(
                {"item_count": items, "items": [], "generated_at": "2026-09-19T00:00:00+00:00"}
            ),
            encoding="utf-8",
        )
    return directory


@pytest.mark.parametrize(
    "layout",
    ["apps/web-explorer", "explorer", "artifacts/explorer", "."],
)
def test_finds_the_explorer_in_every_supported_layout(tmp_path: Path, layout: str) -> None:
    expected = _explorer(tmp_path / layout)
    assert find_explorer_dir(tmp_path) == expected.resolve()


def test_repository_layout_wins_over_a_stray_artifact(tmp_path: Path) -> None:
    repo = _explorer(tmp_path / "apps/web-explorer")
    _explorer(tmp_path / "explorer")
    assert find_explorer_dir(tmp_path) == repo.resolve()


def test_a_directory_without_index_html_is_not_the_explorer(tmp_path: Path) -> None:
    (tmp_path / "explorer" / "data").mkdir(parents=True)
    assert find_explorer_dir(tmp_path) is None


def test_missing_data_is_reported_with_the_command_that_fixes_it(tmp_path: Path) -> None:
    directory = _explorer(tmp_path / "explorer", with_data=False)
    message = describe_data(directory)
    assert "is missing" in message
    assert "archive-export-explorer" in message


def test_present_data_is_summarized(tmp_path: Path) -> None:
    directory = _explorer(tmp_path / "explorer", items=158)
    assert "158 records" in describe_data(directory)


def test_corrupt_data_does_not_raise(tmp_path: Path) -> None:
    directory = _explorer(tmp_path / "explorer")
    (directory / "data" / "explorer.json").write_text("{not json", encoding="utf-8")
    assert "could not be read" in describe_data(directory)


def test_free_port_skips_a_port_already_in_use() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        busy = taken.getsockname()[1]
        assert free_port(busy) != busy


def test_missing_explorer_exits_with_a_clear_code(tmp_path: Path, capsys) -> None:
    assert main(["--root", str(tmp_path), "--no-browser"]) == 2
    assert "Could not find the Explorer" in capsys.readouterr().err


# --- the Windows launcher ----------------------------------------------------


def test_batch_file_is_windows_readable() -> None:
    raw = BAT.read_bytes()
    assert raw, "VIEW_EXPLORER.bat is empty"
    # cmd.exe needs CRLF; a lone LF breaks labels and multi-line blocks.
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
    raw.decode("ascii")  # no smart quotes or stray unicode


def test_batch_file_avoids_the_delayed_expansion_trap() -> None:
    """%ERRORLEVEL% inside a parenthesised block expands at parse time.

    The launcher uses `goto` labels instead, so guard against someone
    reintroducing a nested if-block that silently always takes one branch.
    """

    text = BAT.read_text(encoding="ascii")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("if ") and "%ERRORLEVEL%" in stripped:
            assert stripped.endswith("pause"), (
                f"%ERRORLEVEL% used in a branching line outside a label: {stripped!r}"
            )


def test_batch_file_uses_windows_null_device_not_unix() -> None:
    text = BAT.read_text(encoding="ascii")
    assert "/dev/null" not in text
    assert ">nul" in text


def test_batch_file_delegates_to_the_tested_helper() -> None:
    text = BAT.read_text(encoding="ascii")
    # Beside the batch file (dropped next to an unzipped artifact)...
    assert '"view_explorer.py"' in text
    # ...or in the repository layout.
    assert r"tools\view_explorer.py" in text
    # And still works with no helper at all, where only the artifact exists.
    assert "--directory explorer" in text


def test_batch_file_warns_when_the_read_model_is_absent() -> None:
    """A silently empty page is the worst outcome for a non-technical user."""

    text = BAT.read_text(encoding="ascii")
    assert text.count("is missing; the page will be empty") >= 2


def test_helper_finds_an_artifact_from_the_folder_it_was_dropped_into(tmp_path: Path) -> None:
    """The flow we actually tell people to use: unzip, drop both files, run."""

    _explorer(tmp_path / "explorer", items=158)
    (tmp_path / "VIEW_EXPLORER.bat").write_bytes(BAT.read_bytes())
    (tmp_path / "view_explorer.py").write_text("# copy of the helper", encoding="utf-8")

    found = find_explorer_dir(tmp_path)
    assert found == (tmp_path / "explorer").resolve()
    assert "158 records" in describe_data(found)


def test_candidate_dirs_cover_the_documented_layouts() -> None:
    names = {path.as_posix() for path in CANDIDATE_DIRS}
    assert {"apps/web-explorer", "explorer", "."} <= names
