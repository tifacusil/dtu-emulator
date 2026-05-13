"""replay mode: send pre-recorded scenario messages in order."""

import json
import logging
import time
from pathlib import Path

from ..frame import encode_frame
from ..transport import ACK_STATUS, TCPTransport

logger = logging.getLogger(__name__)


def run_replay(
    scenario_path: Path,
    host: str,
    port: int,
    ack_timeout: float,
    no_retry: bool,
    realtime: bool,
    speedup: float,
) -> None:
    with open(scenario_path) as f:
        scenario = json.load(f)

    messages = scenario["messages"]
    scenario_id = scenario.get("scenario_id", scenario_path.stem)

    transport = TCPTransport(host, port, ack_timeout=ack_timeout, no_retry=no_retry)
    transport.connect()

    stats = {s: 0 for s in ACK_STATUS.values()}
    stats["TIMEOUT"] = 0
    latencies = []
    t_start = time.monotonic()
    prev_ts_ms: int | None = None

    try:
        for i, msg in enumerate(messages):
            if realtime and i > 0:
                from datetime import datetime, timezone
                ts_str = msg["timestamp"].replace("Z", "+00:00")
                ts_ms = int(datetime.fromisoformat(ts_str).timestamp() * 1000)
                if prev_ts_ms is not None:
                    delta_s = (ts_ms - prev_ts_ms) / 1000.0 / speedup
                    if delta_s > 0:
                        time.sleep(delta_s)
                prev_ts_ms = ts_ms

            frame = encode_frame(msg)
            msg_short = msg["message_id"][:8]
            sensor_type = msg["sensor_type"]
            sensor_id = msg["sensor_id"]
            project = msg["project_id"]

            try:
                status, latency_ms = transport.send_with_retry(frame)
                status_name = ACK_STATUS.get(status, f"UNKNOWN({status:#04x})")
                latencies.append(latency_ms)
                stats[status_name] = stats.get(status_name, 0) + 1
                level = logging.INFO if status == 0x00 else logging.WARNING
                logger.log(
                    level,
                    "sent %s/%s (proj=%s, msg_id=%s, size=%dB) → ack=%s in %.0fms",
                    sensor_type, sensor_id, project, msg_short, len(frame), status_name, latency_ms,
                )
            except Exception as exc:
                stats["TIMEOUT"] += 1
                logger.error("frame send failed: %s", exc)

    finally:
        transport.close()

    duration = time.monotonic() - t_start
    sent = len(messages)
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    throughput = sent / duration if duration > 0 else 0.0

    print("\n==== Summary ====")
    print(f"Mode:                  replay")
    print(f"Scenario:              {scenario_id}")
    print(f"Duration:              {duration:.1f}s")
    print(f"Frames sent:           {sent}")
    print(f"ACK status counts:")
    for k, v in stats.items():
        if v > 0:
            print(f"  {k}:{'':>15}{v}")
    print(f"Avg ACK latency:       {avg_latency:.1f}ms")
    print(f"Throughput:            {throughput:.2f} frames/s")
