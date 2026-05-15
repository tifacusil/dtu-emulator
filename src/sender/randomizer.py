"""Random payload generation with ranges from Bai et al. (2020)."""

import math
import uuid
from datetime import datetime, timezone
from random import Random


def now_utc_iso8601() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


FIX_QUALITY_WEIGHTS = [
    ("rtk_fixed", 0.90),
    ("rtk_float", 0.08),
    ("dgps", 0.007),
    ("single", 0.002),
    ("no_fix", 0.001),
]
_FQ_VALUES = [v for v, _ in FIX_QUALITY_WEIGHTS]
_FQ_PROBS = [p for _, p in FIX_QUALITY_WEIGHTS]


def _weighted_choice(rng: Random, values: list, weights: list) -> str:
    r = rng.random()
    cumul = 0.0
    for v, w in zip(values, weights):
        cumul += w
        if r < cumul:
            return v
    return values[-1]


def generate_random_payload(
    sensor_type: str, template_payload: dict, rng: Random
) -> dict:
    if sensor_type == "gnss":
        return _random_gnss(rng)
    elif sensor_type == "rainfall":
        return _random_rainfall(rng, template_payload)
    elif sensor_type == "strain":
        return _random_strain(rng)
    elif sensor_type == "soil_pressure":
        return _random_soil_pressure(rng)
    elif sensor_type == "deep_displacement":
        return _random_deep_displacement(rng, template_payload)
    raise ValueError(f"Unknown sensor_type: {sensor_type}")


def _random_gnss(rng: Random) -> dict:
    x = rng.uniform(-50.0, 50.0)
    y = rng.uniform(-50.0, 50.0)
    z = rng.uniform(-20.0, 20.0)
    h = math.sqrt(x**2 + y**2)
    cumul = rng.uniform(0.0, 3000.0)
    fix = _weighted_choice(rng, _FQ_VALUES, _FQ_PROBS)
    return {
        "displacement_x_mm": x,
        "displacement_y_mm": y,
        "displacement_z_mm": z,
        "displacement_horizontal_mm": h,
        "cumulative_displacement_mm": cumul,
        "fix_quality": fix,
    }


def _random_rainfall(rng: Random, template: dict) -> dict:
    return {
        "rainfall_mm": rng.uniform(0.0, 50.0),
        "cumulative_rainfall_mm": rng.uniform(0.0, 3000.0),
        "interval_minutes": template["interval_minutes"],
    }


def _random_strain(rng: Random) -> dict:
    result = {"strain_microstrain": rng.uniform(-1000.0, 1000.0)}
    if rng.random() < 0.9:
        result["temperature_celsius"] = rng.uniform(5.0, 40.0)
    return result


def _random_soil_pressure(rng: Random) -> dict:
    result = {"pressure_kpa": rng.uniform(0.0, 200.0)}
    if rng.random() < 0.9:
        result["temperature_celsius"] = rng.uniform(5.0, 40.0)
    return result


def _random_deep_displacement(rng: Random, template: dict) -> dict:
    return {
        "depth_m": template["depth_m"],
        "tilt_x_mm": rng.uniform(-50.0, 50.0),
        "tilt_y_mm": rng.uniform(-50.0, 50.0),
        "cumulative_tilt_mm": rng.uniform(0.0, 500.0),
    }


def build_envelope(identity: dict, rng: Random) -> dict:
    sensor_type = identity["sensor_type"]
    payload_identity = identity.get("_payload_identity", {})
    envelope = {
        "schema_version": identity.get("schema_version", "1.0"),
        "message_id": str(uuid.uuid4()),
        "project_id": identity["project_id"],
        "sensor_id": identity["sensor_id"],
        "sensor_type": sensor_type,
        "timestamp": now_utc_iso8601(),
        "sampling_interval_seconds": identity["sampling_interval_seconds"],
        "payload": generate_random_payload(sensor_type, payload_identity, rng),
    }
    return envelope
