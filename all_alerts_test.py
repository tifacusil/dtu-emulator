"""
all_alerts_test.py
------------------
Sends 50 binary TCP frames to the data-receiving service to trigger every
Early Warning alert level (blue, orange, red) for project 'shangtan',
using ONLY sensors that really exist in the data server
(project_management.sensors → GXZM-DB01..DB08, the 8 active GNSS monitoring
points; GXZM-BASE is the fixed reference station and is excluded).

Pipeline:
    this script → TCP:5000 → data-receiving → RabbitMQ → Early Warning → alert

Because Early Warning re-stores the latest reading as the new baseline after
every evaluation, a single sensor can emit many alerts: send one baseline,
then a stream of trigger frames spaced Δt=3600s apart. Each trigger's
speed = Δmm / 3600s * 86400 = Δmm * 24 (mm/day) is compared against the
previous message.

Thresholds (go-early-warning cmd/early-warning/main.go, shangtan, mm/day):
  blue ≥ 10, orange ≥ 15, red ≥ 20

Δmm per level (Δt = 3600s):
  blue   Δmm=0.5 → 12.0 mm/day
  orange Δmm=0.7 → 16.8 mm/day
  red    Δmm=1.0 → 24.0 mm/day

Frame budget = 50: 8 baselines + 42 triggers → 42 alerts, levels rotated
so every sensor sees blue/orange/red.

Usage:
    python3 all_alerts_test.py [--host HOST] [--port PORT]
"""

import copy
import json
import sys
import time
import uuid
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from sender.frame import encode_frame
from sender.transport import TCPTransport, ACK_STATUS

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load contract example as base template
# ---------------------------------------------------------------------------
EXAMPLE_PATH = Path(__file__).parent / "contracts" / "examples" / "gnss-shangtan.json"

with open(EXAMPLE_PATH) as f:
    BASE_EXAMPLE = json.load(f)

# ---------------------------------------------------------------------------
# Test parameters
# ---------------------------------------------------------------------------
TOTAL_FRAMES = 50
STEP_SECONDS = 3600

# Real active GNSS monitoring sensors for project 'shangtan'
# (project_management.sensors; GXZM-BASE reference station excluded).
SENSORS = [
    "GXZM-DB01",
    "GXZM-DB02",
    "GXZM-DB03",
    "GXZM-DB04",
    "GXZM-DB05",
    "GXZM-DB06",
    "GXZM-DB07",
    "GXZM-DB08",
]

# Δmm per level → speed = Δmm / 3600s * 86400 = Δmm * 24 (mm/day)
DELTA_BY_LEVEL = {
    "blue":   0.5,   # 12.0 mm/day  (≥10, <15)
    "orange": 0.7,   # 16.8 mm/day  (≥15, <20)
    "red":    1.0,   # 24.0 mm/day  (≥20)
}
_LEVEL_CYCLE = ["blue", "orange", "red"]

_now = datetime.now(tz=timezone.utc).replace(microsecond=0)

# Per-sensor running state: monotonically increasing timestamp + cumulative mm.
_STATE = {
    sid: {"ts": _now, "cumul": 100.0 + i * 25.0}
    for i, sid in enumerate(SENSORS)
}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_envelope(sensor_id: str, timestamp: str, cumulative_mm: float) -> dict:
    """Build an envelope from the contract example, overriding specific fields."""
    envelope = copy.deepcopy(BASE_EXAMPLE)
    envelope["message_id"] = str(uuid.uuid4())
    envelope["sensor_id"] = sensor_id
    envelope["timestamp"] = timestamp
    envelope["payload"]["cumulative_displacement_mm"] = cumulative_mm
    envelope["payload"]["displacement_horizontal_mm"] = cumulative_mm
    envelope["payload"]["fix_quality"] = "rtk_fixed"
    return envelope


def _send(transport, frame, stats) -> tuple[str, float | None]:
    try:
        status, latency = transport.send_with_retry(frame)
        name = ACK_STATUS.get(status, f"UNKNOWN({status:#04x})")
        stats[name] = stats.get(name, 0) + 1
        return name, latency
    except Exception as exc:
        stats["TIMEOUT"] += 1
        logger.error("send FAILED: %s", exc)
        return "TIMEOUT", None


def run(host: str, port: int, ack_timeout: float) -> None:
    transport = TCPTransport(host, port, ack_timeout=ack_timeout)
    transport.connect()
    logger.info("Connected to %s:%d", host, port)

    stats = {name: 0 for name in ACK_STATUS.values()}
    stats["TIMEOUT"] = 0
    expected = {"blue": 0, "orange": 0, "red": 0}
    frames = 0

    try:
        # --- Phase 1: baseline per sensor (no alert, stored in Redis) ---
        for sid in SENSORS:
            st = _STATE[sid]
            frame = encode_frame(make_envelope(sid, _iso(st["ts"]), st["cumul"]))
            name, latency = _send(transport, frame, stats)
            frames += 1
            logger.info(
                "[baseline %2d] %-9s cumul=%.1fmm  ack=%s  (%s)",
                frames, sid, st["cumul"], name,
                f"{latency:.0f}ms" if latency is not None else "-",
            )
            time.sleep(0.4)

        # --- Phase 2: trigger stream, round-robin over sensors, rotate level ---
        trig = 0
        while frames < TOTAL_FRAMES:
            sid = SENSORS[trig % len(SENSORS)]
            level = _LEVEL_CYCLE[trig % len(_LEVEL_CYCLE)]
            delta = DELTA_BY_LEVEL[level]
            speed = delta * 24.0

            st = _STATE[sid]
            st["ts"] = st["ts"] + timedelta(seconds=STEP_SECONDS)
            st["cumul"] += delta

            frame = encode_frame(make_envelope(sid, _iso(st["ts"]), st["cumul"]))
            name, latency = _send(transport, frame, stats)
            frames += 1
            trig += 1
            if name == "OK":
                expected[level] += 1
            logger.info(
                "[trigger  %2d] %-9s cumul=%.1fmm  speed=%.1fmm/day  ack=%s  (%s)  → %s",
                frames, sid, st["cumul"], speed, name,
                f"{latency:.0f}ms" if latency is not None else "-",
                level.upper(),
            )
            time.sleep(0.4)

    finally:
        transport.close()

    total_alerts = sum(expected.values())
    print("\n==== Summary ====")
    print(f"Project:               shangtan")
    print(f"Real sensors used:     {len(SENSORS)}  ({', '.join(SENSORS)})")
    print(f"Total frames sent:     {frames}")
    print(f"Alerts expected:       {total_alerts}")
    print(f"  blue:                {expected['blue']}")
    print(f"  orange:              {expected['orange']}")
    print(f"  red:                 {expected['red']}")
    print("ACK status counts:")
    for k, v in stats.items():
        if v > 0:
            print(f"  {k}:{v:>20}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="All-alerts test — blue/orange/red on real Shangtan GNSS sensors (50 frames)"
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--ack-timeout", type=float, default=5.0, metavar="SEC")
    args = parser.parse_args()

    run(args.host, args.port, args.ack_timeout)


if __name__ == "__main__":
    main()
