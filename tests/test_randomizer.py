import math
from random import Random

from sender.envelope import extract_identity
from sender.randomizer import build_envelope, generate_random_payload


def _envelopes(example, seed, count):
    identity = extract_identity(example)
    rng = Random(seed)
    return [build_envelope(identity, rng) for _ in range(count)]


def test_seed_reproducibility(gnss_example):
    run1 = _envelopes(gnss_example, 42, 5)
    run2 = _envelopes(gnss_example, 42, 5)
    for e1, e2 in zip(run1, run2):
        assert e1["payload"] == e2["payload"]
        assert e1["project_id"] == e2["project_id"]
        assert e1["sensor_id"] == e2["sensor_id"]


def test_identity_preserved(any_example):
    identity = extract_identity(any_example)
    rng = Random(1)
    for _ in range(10):
        env = build_envelope(identity, rng)
        assert env["project_id"] == any_example["project_id"]
        assert env["sensor_id"] == any_example["sensor_id"]
        assert env["sensor_type"] == any_example["sensor_type"]
        assert (
            env["sampling_interval_seconds"] == any_example["sampling_interval_seconds"]
        )


def test_measurement_in_range_gnss():
    rng = Random(0)
    for _ in range(50):
        p = generate_random_payload("gnss", {}, rng)
        assert -50.0 <= p["displacement_x_mm"] <= 50.0
        assert -50.0 <= p["displacement_y_mm"] <= 50.0
        assert -20.0 <= p["displacement_z_mm"] <= 20.0
        assert p["displacement_horizontal_mm"] >= 0
        assert 0 <= p["cumulative_displacement_mm"] <= 3000.0
        assert p["fix_quality"] in {
            "rtk_fixed",
            "rtk_float",
            "dgps",
            "single",
            "no_fix",
        }


def test_measurement_in_range_rainfall():
    rng = Random(0)
    template = {"interval_minutes": 60}
    for _ in range(50):
        p = generate_random_payload("rainfall", template, rng)
        assert 0 <= p["rainfall_mm"] <= 50.0
        assert 0 <= p["cumulative_rainfall_mm"] <= 3000.0
        assert p["interval_minutes"] == 60


def test_measurement_in_range_strain():
    rng = Random(0)
    for _ in range(50):
        p = generate_random_payload("strain", {}, rng)
        assert -1000.0 <= p["strain_microstrain"] <= 1000.0
        if "temperature_celsius" in p:
            assert 5.0 <= p["temperature_celsius"] <= 40.0


def test_measurement_in_range_soil_pressure():
    rng = Random(0)
    for _ in range(50):
        p = generate_random_payload("soil_pressure", {}, rng)
        assert 0 <= p["pressure_kpa"] <= 200.0
        if "temperature_celsius" in p:
            assert 5.0 <= p["temperature_celsius"] <= 40.0


def test_measurement_in_range_deep_displacement():
    rng = Random(0)
    template = {"depth_m": 15.0}
    for _ in range(50):
        p = generate_random_payload("deep_displacement", template, rng)
        assert p["depth_m"] == 15.0
        assert -50.0 <= p["tilt_x_mm"] <= 50.0
        assert -50.0 <= p["tilt_y_mm"] <= 50.0
        assert 0 <= p["cumulative_tilt_mm"] <= 500.0


def test_horizontal_consistency():
    rng = Random(99)
    for _ in range(50):
        p = generate_random_payload("gnss", {}, rng)
        expected_h = math.sqrt(
            p["displacement_x_mm"] ** 2 + p["displacement_y_mm"] ** 2
        )
        assert math.isclose(p["displacement_horizontal_mm"], expected_h, rel_tol=1e-6)


def test_fix_quality_dominance():
    rng = Random(7)
    counts = {}
    for _ in range(1000):
        p = generate_random_payload("gnss", {}, rng)
        fq = p["fix_quality"]
        counts[fq] = counts.get(fq, 0) + 1
    assert counts.get("rtk_fixed", 0) > 800


def test_temperature_optional_presence():
    rng = Random(3)
    has_temp = sum(
        1
        for _ in range(200)
        if "temperature_celsius" in generate_random_payload("strain", {}, rng)
    )
    assert 150 < has_temp < 200
