import pytest

from sender.cli import build_parser


def test_fixture_mode_defaults(tmp_path):
    f = tmp_path / "example.json"
    f.write_text("{}")
    args = build_parser().parse_args(["fixture", "--file", str(f)])
    assert args.mode == "fixture"
    assert args.file == f
    assert args.count == 1
    assert args.rate == 1.0
    assert args.seed is None
    assert args.corrupt is None
    assert args.corrupt_count == 8
    assert args.host == "localhost"
    assert args.port == 5000
    assert args.ack_timeout == 5.0
    assert args.no_retry is False


def test_fixture_mode_explicit_args(tmp_path):
    f = tmp_path / "example.json"
    f.write_text("{}")
    args = build_parser().parse_args(
        [
            "fixture",
            "--file",
            str(f),
            "--count",
            "10",
            "--rate",
            "2.5",
            "--seed",
            "42",
            "--corrupt",
            "crc",
            "--corrupt-count",
            "4",
            "--host",
            "192.168.1.1",
            "--port",
            "9000",
            "--ack-timeout",
            "3.0",
            "--no-retry",
        ]
    )
    assert args.count == 10
    assert args.rate == 2.5
    assert args.seed == 42
    assert args.corrupt == "crc"
    assert args.corrupt_count == 4
    assert args.host == "192.168.1.1"
    assert args.port == 9000
    assert args.ack_timeout == 3.0
    assert args.no_retry is True


def test_replay_mode_defaults(tmp_path):
    s = tmp_path / "scenario.json"
    s.write_text("{}")
    args = build_parser().parse_args(["replay", "--scenario", str(s)])
    assert args.mode == "replay"
    assert args.scenario == s
    assert args.realtime is False
    assert args.speedup == 1.0


def test_replay_mode_realtime(tmp_path):
    s = tmp_path / "scenario.json"
    s.write_text("{}")
    args = build_parser().parse_args(
        [
            "replay",
            "--scenario",
            str(s),
            "--realtime",
            "--speedup",
            "2.0",
        ]
    )
    assert args.realtime is True
    assert args.speedup == 2.0


def test_mode_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_all_corrupt_choices(tmp_path):
    f = tmp_path / "example.json"
    f.write_text("{}")
    for choice in [
        "crc",
        "sync_start",
        "sync_end",
        "length",
        "version",
        "type",
        "schema",
        "random",
    ]:
        args = build_parser().parse_args(
            ["fixture", "--file", str(f), "--corrupt", choice]
        )
        assert args.corrupt == choice
