from archive.cli import build_parser


def test_internet_archive_source_collection_does_not_override_engine_collection(tmp_path):
    args = build_parser().parse_args(
        ["sample-internet-archive", "--output", str(tmp_path / "ia.jsonl")]
    )

    assert args.collection is None
    assert args.ia_collection == "911"


def test_engine_and_internet_archive_collection_flags_can_coexist(tmp_path):
    args = build_parser().parse_args(
        [
            "--collection",
            "wikileaks",
            "sample-internet-archive",
            "--collection",
            "911",
            "--output",
            str(tmp_path / "ia.jsonl"),
        ]
    )

    assert args.collection == "wikileaks"
    assert args.ia_collection == "911"


def test_911da_source_collection_does_not_override_engine_collection(tmp_path):
    args = build_parser().parse_args(
        [
            "sample-911da",
            "--collection",
            "267",
            "--output",
            str(tmp_path / "voices.jsonl"),
        ]
    )

    assert args.collection is None
    assert args.source_collection_id == 267
