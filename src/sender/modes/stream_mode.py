"""stream mode: read frame-send requests as JSON lines from stdin, hold one
persistent TCP connection, write one JSON-line ACK result per request to
stdout.

Used by the Artillery load-test engine's worker pool so a single long-lived
Python process (and TCP connection) serves many VUs' `send` steps instead of
paying interpreter-startup cost per frame — see
tesis-infra/load-tests/README-engine.md.

Request line:  {"file": "<contract-example-path>", "seed": <int|null>,
                 "corrupt": "<kind>|null", "corrupt_count": <int>,
                 "sensor_id": "<id>|null", "reading_index": <int>}
Response line: {"status": "OK", "latency_ms": 12.3} or {"error": "<message>"}

`sensor_id` selects the field corpus: the frame becomes the `reading_index`-th
reading of that sensor's displacement series (see field.py), instead of the
per-frame random payload of the contract example's single sensor. The caller
owns fleet composition and reading order; this worker only renders the reading,
which is why it can be respawned or swapped mid-run without losing a series.
"""

import json
import logging
import sys
import time
from pathlib import Path
from random import Random

from ..corruption import corrupt_frame
from ..envelope import extract_identity
from ..field import Fleet
from ..frame import encode_frame
from ..randomizer import build_envelope
from ..transport import ACK_STATUS, TCPTransport
from .fixture_mode import _load_example

logger = logging.getLogger(__name__)

_identity_cache: dict[str, dict] = {}


def _get_identity(file_path: str) -> dict:
    identity = _identity_cache.get(file_path)
    if identity is None:
        example = _load_example(Path(file_path))
        identity = extract_identity(example)
        _identity_cache[file_path] = identity
    return identity


def _handle_request(
    transport: TCPTransport,
    request: dict,
    rng: Random,
    corrupt_rng: Random,
    fleet: Fleet,
) -> dict:
    identity = _get_identity(request["file"])
    seed = request.get("seed")
    envelope_rng = Random(seed) if seed is not None else rng
    sensor_id = request.get("sensor_id")
    if sensor_id:
        envelope = fleet.build_envelope(
            identity, sensor_id, int(request.get("reading_index", 0)), envelope_rng
        )
    else:
        envelope = build_envelope(identity, envelope_rng)
    frame = encode_frame(envelope)

    corrupt = request.get("corrupt")
    if corrupt:
        frame_corrupt_rng = Random(seed) if seed is not None else corrupt_rng
        frame = corrupt_frame(
            frame,
            corrupt,
            random_count=request.get("corrupt_count", 8),
            rng=frame_corrupt_rng,
        )

    status, latency_ms = transport.send_with_retry(frame)
    status_name = ACK_STATUS.get(status, f"UNKNOWN({status:#04x})")
    return {"status": status_name, "latency_ms": latency_ms}


def run_stream(host: str, port: int, ack_timeout: float, no_retry: bool) -> None:
    transport = TCPTransport(host, port, ack_timeout=ack_timeout, no_retry=no_retry)
    rng = Random()
    corrupt_rng = Random()
    fleet = Fleet()

    stats: dict[str, int] = {}
    sent = 0
    t_start = time.monotonic()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            sent += 1
            try:
                request = json.loads(line)
                result = _handle_request(transport, request, rng, corrupt_rng, fleet)
                stats[result["status"]] = stats.get(result["status"], 0) + 1
            except Exception as exc:
                stats["ERROR"] = stats.get("ERROR", 0) + 1
                result = {"error": str(exc)}

            sys.stdout.write(json.dumps(result) + "\n")
            sys.stdout.flush()
    finally:
        transport.close()

    duration = time.monotonic() - t_start
    logger.info(
        "stream worker exiting: %d requests in %.1fs (%s)",
        sent,
        duration,
        ", ".join(f"{k}={v}" for k, v in stats.items()),
    )
