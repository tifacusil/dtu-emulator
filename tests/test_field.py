import math
from datetime import timedelta
from random import Random

from sender.envelope import extract_identity
from sender.field import (
    CREEP_MM_DAY,
    FLEET_EPOCH,
    Fleet,
    SensorProfile,
    sensor_id_for,
)

# Shangtan thresholds from Bai et al. (2020), as configured in both
# early-warning implementations.
BLUE_MM_DAY = 10.0
RED_MM_DAY = 20.0


def _profile(sensor_id="GXZM-DB007", interval=3600):
    return SensorProfile(sensor_id, interval)


def test_sensor_ids_are_distinct_and_follow_the_paper_convention():
    ids = [sensor_id_for(i) for i in range(1000)]
    assert len(set(ids)) == 1000
    assert ids[3] == "GXZM-DB003"
    assert all(len(i) <= 64 for i in ids)


def test_profile_is_a_function_of_the_sensor_id_alone():
    a, b = _profile(), _profile()
    for index in (0, 1, 17, 500, 4321):
        assert a.cumulative_mm(index) == b.cumulative_mm(index)
        assert a.timestamp(index) == b.timestamp(index)


def test_different_sensors_get_different_series():
    first = _profile("GXZM-DB001").cumulative_mm(100)
    second = _profile("GXZM-DB002").cumulative_mm(100)
    assert first != second


def test_cumulative_displacement_is_monotonic():
    profile = _profile()
    previous = profile.cumulative_mm(0)
    for index in range(1, 3 * 240):
        current = profile.cumulative_mm(index)
        assert current >= previous
        previous = current


def test_cumulative_is_positive():
    for sensor in range(20):
        profile = _profile(sensor_id_for(sensor))
        assert profile.cumulative_mm(0) > 0.0


def test_random_access_matches_sequential_walk():
    """A reading must not depend on which readings were rendered before it.

    This is what lets any worker in the pool serve any sensor, and a respawned
    worker resume a series it never started.
    """
    walked = _profile()
    sequential = [walked.cumulative_mm(i) for i in range(600)]
    for index in (599, 3, 240, 0, 241, 120):
        assert _profile().cumulative_mm(index) == sequential[index]


def test_timestamps_advance_by_one_sampling_interval():
    profile = _profile(interval=3600)
    for index in range(50):
        expected = profile.timestamp(0) + timedelta(seconds=3600 * index)
        assert profile.timestamp(index) == expected


def test_timestamps_stay_in_the_papers_monitoring_window():
    profile = _profile()
    assert FLEET_EPOCH <= profile.timestamp(0) < FLEET_EPOCH + timedelta(seconds=3600)


def test_quiet_creep_stays_below_the_lowest_threshold():
    """A sensor outside a deformation event must not alert on creep alone."""
    for sensor in range(50):
        profile = _profile(sensor_id_for(sensor))
        assert CREEP_MM_DAY[0] <= profile.creep_mm_day <= CREEP_MM_DAY[1]
        assert profile.creep_mm_day < BLUE_MM_DAY


def _speed_between(profile, index):
    delta = profile.cumulative_mm(index) - profile.cumulative_mm(index - 1)
    dt = (profile.timestamp(index) - profile.timestamp(index - 1)).total_seconds()
    return delta / dt * 86400.0


def test_reported_speed_matches_the_series_the_engines_will_see():
    profile = _profile()
    for index in range(1, 500):
        assert math.isclose(
            _speed_between(profile, index), profile.speed_mm_day(index), rel_tol=1e-9
        )


def test_alerts_are_occasional_not_the_norm():
    """The whole point of the corpus fix: crossing a threshold is an event.

    With the pre-fix corpus (uniform per-frame cumulative displacement) roughly
    half of all evaluations alerted and every one of them was a `red`.
    """
    total = 0
    alerting = 0
    red = 0
    for sensor in range(40):
        profile = _profile(sensor_id_for(sensor))
        for index in range(1, 480):
            speed = _speed_between(profile, index)
            total += 1
            if speed >= BLUE_MM_DAY:
                alerting += 1
            if speed >= RED_MM_DAY:
                red += 1
    rate = alerting / total
    assert 0.001 < rate < 0.10, rate
    # And the alerts that do fire are spread across levels, not all `red`.
    assert 0 < red < alerting


def test_envelope_is_shaped_like_the_contract_example(gnss_example):
    identity = extract_identity(gnss_example)
    envelope = Fleet().build_envelope(identity, "GXZM-DB042", 7, Random(1))
    assert envelope.keys() == gnss_example.keys() - {"received_at"}
    assert envelope["payload"].keys() == gnss_example["payload"].keys()
    assert envelope["sensor_id"] == "GXZM-DB042"
    assert envelope["project_id"] == gnss_example["project_id"]
    assert envelope["sensor_type"] == "gnss"
    assert envelope["timestamp"].endswith("Z")


def test_horizontal_component_is_consistent(gnss_example):
    identity = extract_identity(gnss_example)
    fleet = Fleet()
    for index in range(30):
        payload = fleet.build_envelope(identity, "GXZM-DB005", index, Random(index))[
            "payload"
        ]
        expected = math.sqrt(
            payload["displacement_x_mm"] ** 2 + payload["displacement_y_mm"] ** 2
        )
        assert math.isclose(payload["displacement_horizontal_mm"], expected)
        assert payload["cumulative_displacement_mm"] >= 0.0
        assert payload["fix_quality"] in {
            "rtk_fixed",
            "rtk_float",
            "dgps",
            "single",
            "no_fix",
        }


def test_message_id_is_unique_per_frame(gnss_example):
    identity = extract_identity(gnss_example)
    fleet = Fleet()
    ids = {
        fleet.build_envelope(identity, "GXZM-DB001", 3, Random(0))["message_id"]
        for _ in range(20)
    }
    assert len(ids) == 20


def test_non_gnss_sensors_fall_back_to_the_random_payload(rainfall_example):
    identity = extract_identity(rainfall_example)
    envelope = Fleet().build_envelope(identity, "GXZM-RG09", 4, Random(3))
    assert envelope["sensor_id"] == "GXZM-RG09"
    assert envelope["sensor_type"] == "rainfall"
    assert set(envelope["payload"]) == set(rainfall_example["payload"])


def test_fleet_reuses_profiles_and_reprofiles_on_interval_change():
    fleet = Fleet()
    first = fleet.profile("GXZM-DB001", 3600)
    assert fleet.profile("GXZM-DB001", 3600) is first
    assert fleet.profile("GXZM-DB001", 900) is not first
