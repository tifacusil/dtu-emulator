"""CLI argument parsing and dispatch."""

import argparse
import logging
from pathlib import Path


def _common_network_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--ack-timeout", type=float, default=5.0, metavar="SEC")
    p.add_argument("--no-retry", action="store_true")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sender", description="DTU simulator")
    sub = parser.add_subparsers(dest="mode", required=True)

    # fixture
    fix = sub.add_parser("fixture", help="Send random envelopes generated from a contract example")
    fix.add_argument("--file", required=True, type=Path, metavar="PATH")
    fix.add_argument("--count", type=int, default=1, metavar="N")
    fix.add_argument("--rate", type=float, default=1.0, metavar="N")
    fix.add_argument("--seed", type=int, default=None, metavar="N")
    fix.add_argument(
        "--corrupt",
        choices=["crc", "sync_start", "sync_end", "length", "version", "type", "schema", "random"],
        default=None,
    )
    fix.add_argument("--corrupt-count", type=int, default=8, metavar="N")
    _common_network_args(fix)

    # replay
    rep = sub.add_parser("replay", help="Replay a pre-recorded scenario")
    rep.add_argument("--scenario", required=True, type=Path, metavar="PATH")
    rep.add_argument("--realtime", action="store_true")
    rep.add_argument("--speedup", type=float, default=1.0, metavar="N")
    _common_network_args(rep)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    if args.mode == "fixture":
        from .modes.fixture_mode import run_fixture
        run_fixture(
            file_path=args.file,
            host=args.host,
            port=args.port,
            count=args.count,
            rate=args.rate,
            seed=args.seed,
            corrupt=args.corrupt,
            corrupt_count=args.corrupt_count,
            ack_timeout=args.ack_timeout,
            no_retry=args.no_retry,
        )

    elif args.mode == "replay":
        from .modes.replay_mode import run_replay
        run_replay(
            scenario_path=args.scenario,
            host=args.host,
            port=args.port,
            ack_timeout=args.ack_timeout,
            no_retry=args.no_retry,
            realtime=args.realtime,
            speedup=args.speedup,
        )
