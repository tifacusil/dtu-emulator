"""fixture mode: generate random envelopes from a contract example and send them."""

import json
import logging
import time
from pathlib import Path
from random import Random

from ..corruption import corrupt_frame
from ..envelope import extract_identity
from ..frame import encode_frame
from ..randomizer import build_envelope
from ..transport import ACK_STATUS, TCPTransport

logger = logging.getLogger(__name__)

_CORRUPT_LABEL = {
    None: None,
    "crc": "crc",
    "sync_start": "sync_start",
    "sync_end": "sync_end",
    "length": "length",
    "version": "version",
    "type": "type",
    "schema": "schema",
    "random": "random",
}


def _load_example(file_path: Path) -> dict:
    with open(file_path) as f:
        data = json.load(f)
    try:
        import jsonschema  # noqa: F401

        _sanity_check(data)
    except ImportError:
        pass
    return data


def _sanity_check(envelope: dict) -> None:
    try:
        import jsonschema

        contracts_dir = Path(__file__).parents[3] / "contracts"
        schema_file = contracts_dir / "schemas" / "envelope.schema.json"
        if schema_file.exists():
            with open(schema_file) as f:
                schema = json.load(f)
            registry = _build_registry(contracts_dir)
            validator = jsonschema.Draft202012Validator(schema, registry=registry)
            validator.validate(envelope)
    except Exception as exc:
        logger.warning("Schema sanity check failed: %s", exc)
        raise


def _build_registry(contracts_dir: Path):
    try:
        from jsonschema import referencing

        resources = []
        for schema_file in (contracts_dir / "schemas").glob("*.schema.json"):
            with open(schema_file) as f:
                schema = json.load(f)
            uri = schema.get("$id", schema_file.name)
            resources.append((uri, referencing.Resource.from_contents(schema)))
        registry = referencing.Registry().with_resources(resources)
        return registry
    except Exception:
        return None


def run_fixture(
    file_path: Path,
    host: str,
    port: int,
    count: int,
    rate: float,
    seed: int | None,
    corrupt: str | None,
    corrupt_count: int,
    ack_timeout: float,
    no_retry: bool,
) -> None:
    example = _load_example(file_path)
    identity = extract_identity(example)
    rng = Random(seed) if seed is not None else Random()
    corrupt_rng = Random(seed) if seed is not None else Random()

    transport = TCPTransport(host, port, ack_timeout=ack_timeout, no_retry=no_retry)
    transport.connect()

    stats = {s: 0 for s in ACK_STATUS.values()}
    stats["TIMEOUT"] = 0
    latencies = []
    t_start = time.monotonic()
    interval = 1.0 / rate if rate > 0 else 0.0

    sent = 0
    try:
        while count == 0 or sent < count:
            t_loop = time.monotonic()
            envelope = build_envelope(identity, rng)
            frame = encode_frame(envelope)

            if corrupt:
                frame = corrupt_frame(
                    frame, corrupt, random_count=corrupt_count, rng=corrupt_rng
                )

            msg_short = envelope["message_id"][:8]
            sensor_type = envelope["sensor_type"]
            sensor_id = envelope["sensor_id"]
            project = envelope["project_id"]

            try:
                status, latency_ms = transport.send_with_retry(frame)
                status_name = ACK_STATUS.get(status, f"UNKNOWN({status:#04x})")
                latencies.append(latency_ms)
                stats[status_name] = stats.get(status_name, 0) + 1
                level = logging.INFO if status == 0x00 else logging.WARNING
                corrupt_tag = f"  [intentional: {corrupt}]" if corrupt else ""
                logger.log(
                    level,
                    "sent %s/%s (proj=%s, msg_id=%s, size=%dB) → ack=%s in %.0fms%s",
                    sensor_type,
                    sensor_id,
                    project,
                    msg_short,
                    len(frame),
                    status_name,
                    latency_ms,
                    corrupt_tag,
                )
            except Exception as exc:
                stats["TIMEOUT"] += 1
                logger.error("frame send failed: %s", exc)

            sent += 1
            if interval > 0:
                elapsed = time.monotonic() - t_loop
                sleep_time = interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
    finally:
        transport.close()

    duration = time.monotonic() - t_start
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    throughput = sent / duration if duration > 0 else 0.0

    print("\n==== Summary ====")
    print("Mode:                  fixture")
    print(f"Source:                {file_path}")
    print(f"Duration:              {duration:.1f}s")
    print(f"Frames sent:           {sent}")
    print("ACK status counts:")
    for k, v in stats.items():
        if v > 0:
            print(f"  {k}:{'':>15}{v}")
    print(f"Avg ACK latency:       {avg_latency:.1f}ms")
    print(f"Throughput:            {throughput:.2f} frames/s")
