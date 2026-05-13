import math

import pytest

from sender.payloads import encode_payload, decode_payload, FIX_QUALITY_ENC, FIX_QUALITY_DEC


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-4)


def _roundtrip(sensor_type, payload):
    encoded = encode_payload(sensor_type, payload)
    return decode_payload(sensor_type, encoded)


def test_gnss_roundtrip(gnss_example):
    p = gnss_example["payload"]
    out = _roundtrip("gnss", p)
    assert _close(out["displacement_x_mm"], p["displacement_x_mm"])
    assert _close(out["displacement_y_mm"], p["displacement_y_mm"])
    assert _close(out["displacement_z_mm"], p["displacement_z_mm"])
    assert _close(out["displacement_horizontal_mm"], p["displacement_horizontal_mm"])
    assert _close(out["cumulative_displacement_mm"], p["cumulative_displacement_mm"])
    assert out["fix_quality"] == p["fix_quality"]


def test_rainfall_roundtrip(rainfall_example):
    p = rainfall_example["payload"]
    out = _roundtrip("rainfall", p)
    assert _close(out["rainfall_mm"], p["rainfall_mm"])
    assert _close(out["cumulative_rainfall_mm"], p["cumulative_rainfall_mm"])
    assert out["interval_minutes"] == p["interval_minutes"]


def test_strain_roundtrip(strain_example):
    p = strain_example["payload"]
    out = _roundtrip("strain", p)
    assert _close(out["strain_microstrain"], p["strain_microstrain"])
    assert _close(out["temperature_celsius"], p["temperature_celsius"])


def test_strain_without_temperature():
    p = {"strain_microstrain": 123.4}
    out = _roundtrip("strain", p)
    assert _close(out["strain_microstrain"], p["strain_microstrain"])
    assert "temperature_celsius" not in out


def test_soil_pressure_roundtrip(soil_pressure_example):
    p = soil_pressure_example["payload"]
    out = _roundtrip("soil_pressure", p)
    assert _close(out["pressure_kpa"], p["pressure_kpa"])
    assert _close(out["temperature_celsius"], p["temperature_celsius"])


def test_soil_pressure_without_temperature():
    p = {"pressure_kpa": 75.0}
    out = _roundtrip("soil_pressure", p)
    assert _close(out["pressure_kpa"], p["pressure_kpa"])
    assert "temperature_celsius" not in out


def test_deep_displacement_roundtrip(deep_displacement_example):
    p = deep_displacement_example["payload"]
    out = _roundtrip("deep_displacement", p)
    assert _close(out["depth_m"], p["depth_m"])
    assert _close(out["tilt_x_mm"], p["tilt_x_mm"])
    assert _close(out["tilt_y_mm"], p["tilt_y_mm"])
    assert _close(out["cumulative_tilt_mm"], p["cumulative_tilt_mm"])


def test_fix_quality_mapping():
    for name, code in FIX_QUALITY_ENC.items():
        assert FIX_QUALITY_DEC[code] == name, f"Bidirectional failure for {name}"
    assert len(FIX_QUALITY_ENC) == 5
