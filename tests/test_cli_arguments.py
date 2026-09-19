"""CLI argument wiring.

The engine-level ``--collection`` and the two long-standing source-level
``--collection`` flags share a spelling. They must not share a dest: argparse
lets a subparser overwrite a parent's value, which silently turned
``archive-ingest sample-internet-archive`` into a lookup for a collection
named "911".
"""

from __future__ import annotations

import pytest

from archive.cli import build_parser
from archive.collections_compat import resolve_collection


@pytest.fixture()
def parser():
    return build_parser()


def test_source_collection_does_not_select_the_engine_collection(parser) -> None:
    args = parser.parse_args(
        ["sample-911da", "--collection", "267", "--output", "o.jsonl"]
    )
    assert args.source_collection == 267
    assert args.engine_collection is None
    assert resolve_collection(args.engine_collection).id == "september11"


def test_internet_archive_default_slug_is_not_a_collection_id(parser) -> None:
    args = parser.parse_args(["sample-internet-archive", "--output", "o.jsonl"])
    assert args.source_collection == "911"
    assert args.engine_collection is None
    assert resolve_collection(args.engine_collection).id == "september11"


def test_both_flags_can_be_used_at_once(parser) -> None:
    args = parser.parse_args(
        [
            "--collection",
            "demo_history",
            "sample-internet-archive",
            "--collection",
            "911",
            "--output",
            "o.jsonl",
        ]
    )
    assert args.engine_collection == "demo_history"
    assert args.source_collection == "911"


def test_source_collection_has_an_unambiguous_alias(parser) -> None:
    args = parser.parse_args(
        ["sample-911da", "--source-collection", "11", "--output", "o.jsonl"]
    )
    assert args.source_collection == 11


def test_engine_collection_selects_the_collection(parser) -> None:
    args = parser.parse_args(["--collection", "demo_history", "list-sources"])
    assert resolve_collection(args.engine_collection).id == "demo_history"


def test_no_subcommand_shadows_the_engine_collection_dest(parser) -> None:
    """Guard against a future subcommand reintroducing the collision."""

    subparsers = next(
        action for action in parser._actions if hasattr(action, "choices") and action.choices
    )
    offenders = [
        name
        for name, sub in subparsers.choices.items()
        for action in sub._actions
        if action.dest == "engine_collection"
    ]
    assert not offenders, f"subcommands shadowing the engine collection: {offenders}"


def test_a_non_collection_value_is_rejected_rather_than_passed_through() -> None:
    with pytest.raises(TypeError, match="collection id or a Collection"):
        resolve_collection(267)
