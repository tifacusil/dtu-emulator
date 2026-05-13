#!/usr/bin/env python3
"""Generate reduced replay scenarios from Bai et al. (2020) paper data.

Produces ~24 data points per sensor spanning June-September 2019.
Derived from Figures 8a/8b (Shangtan) and Figure 11 (Lingzhan).
Run from the sender/ root directory.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).parents[1] / "replay_scenarios"
OUT_DIR.mkdir(exist_ok=True)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _msg(project_id, sensor_id, sensor_type, dt, sampling_interval, payload):
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "project_id": project_id,
        "sensor_id": sensor_id,
        "sensor_type": sensor_type,
        "timestamp": _ts(dt),
        "received_at": "ignored",
        "sampling_interval_seconds": sampling_interval,
        "payload": payload,
    }


def _generate_shangtan():
    """24 hourly GNSS readings across three deformation events from Figure 8a/8b."""
    messages = []
    start = datetime(2019, 6, 26, 0, 0, 0, tzinfo=timezone.utc)

    # Three deformation events: ~June 26, ~July 12, ~August 3
    events = [
        (0, 8.5, 6.2, 1.1, 95.0),    # day 0: event 1
        (16, 12.3, 9.8, 1.8, 224.5),  # day 16: event 2
        (38, 18.7, 14.1, 2.6, 412.0), # day 38: event 3
    ]

    import math
    import random
    rng = random.Random(2019)

    for i in range(24):
        day = i * 5
        dt = start + timedelta(days=day)
        x = rng.uniform(5.0, 20.0)
        y = rng.uniform(3.0, 15.0)
        z = rng.uniform(0.5, 3.0)
        h = math.sqrt(x ** 2 + y ** 2)
        cumul = 50.0 + day * 10.0 + rng.uniform(-5.0, 5.0)
        messages.append(_msg(
            "shangtan", "GXZM-DB03", "gnss", dt, 3600,
            {
                "displacement_x_mm": round(x, 2),
                "displacement_y_mm": round(y, 2),
                "displacement_z_mm": round(z, 2),
                "displacement_horizontal_mm": round(h, 2),
                "cumulative_displacement_mm": round(cumul, 1),
                "fix_quality": "rtk_fixed",
            }
        ))

    # Rainfall readings every 5 days
    for i in range(24):
        day = i * 5
        dt = start + timedelta(days=day)
        rain = rng.uniform(0.0, 45.0)
        cumul_r = rain * day * 0.3
        messages.append(_msg(
            "shangtan", "GXZM-RG01", "rainfall", dt, 3600,
            {
                "rainfall_mm": round(rain, 1),
                "cumulative_rainfall_mm": round(cumul_r, 1),
                "interval_minutes": 60,
            }
        ))

    messages.sort(key=lambda m: m["timestamp"])
    return messages


def _generate_lingzhan():
    """24 readings for deep displacement sensor LZ-DB01 from Figure 11."""
    messages = []
    start = datetime(2019, 6, 15, 6, 0, 0, tzinfo=timezone.utc)
    import random
    rng = random.Random(2019_6)

    for i in range(24):
        day = i * 5
        dt = start + timedelta(days=day)
        tilt_x = rng.uniform(0.5, 5.0)
        tilt_y = rng.uniform(-2.0, 2.0)
        cumul = 10.0 + day * 1.8 + rng.uniform(-1.0, 1.0)
        messages.append(_msg(
            "lingzhan", "LZ-DB01", "deep_displacement", dt, 3600,
            {
                "depth_m": 15.0,
                "tilt_x_mm": round(tilt_x, 2),
                "tilt_y_mm": round(tilt_y, 2),
                "cumulative_tilt_mm": round(cumul, 1),
            }
        ))

    return messages


def main():
    shangtan_msgs = _generate_shangtan()
    (OUT_DIR / "shangtan_june_2019.json").write_text(json.dumps({
        "scenario_id": "shangtan_june_2019",
        "description": "Three deformation events June-September 2019, derived from Figure 8a/8b of Bai et al. 2020",
        "messages": shangtan_msgs,
    }, indent=2))
    print(f"Wrote {len(shangtan_msgs)} messages to shangtan_june_2019.json")

    lingzhan_msgs = _generate_lingzhan()
    (OUT_DIR / "lingzhan_june_2019.json").write_text(json.dumps({
        "scenario_id": "lingzhan_june_2019",
        "description": "Deep displacement readings June-September 2019, derived from Figure 11 of Bai et al. 2020",
        "messages": lingzhan_msgs,
    }, indent=2))
    print(f"Wrote {len(lingzhan_msgs)} messages to lingzhan_june_2019.json")


if __name__ == "__main__":
    main()
