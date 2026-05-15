import uuid
from pathlib import Path

from sender.envelope import encode_header, decode_header, extract_identity

EXAMPLES_DIR = Path(__file__).parents[1] / "contracts" / "examples"


def test_uuid_roundtrip():
    original = str(uuid.uuid4())
    envelope = {
        "message_id": original,
        "project_id": "test",
        "sensor_id": "S01",
        "timestamp": "2026-05-02T14:30:00Z",
        "sampling_interval_seconds": 3600,
    }
    encoded = encode_header(envelope)
    decoded, _ = decode_header(encoded)
    assert decoded["message_id"] == original


def test_timestamp_roundtrip():
    ts = "2026-05-02T14:30:00Z"
    import uuid as _uuid

    envelope = {
        "message_id": str(_uuid.uuid4()),
        "project_id": "shangtan",
        "sensor_id": "GXZM-DB03",
        "timestamp": ts,
        "sampling_interval_seconds": 3600,
    }
    encoded = encode_header(envelope)
    decoded, _ = decode_header(encoded)
    assert decoded["timestamp"] == ts


def test_identity_extraction_gnss(gnss_example):
    identity = extract_identity(gnss_example)
    assert identity["project_id"] == "shangtan"
    assert identity["sensor_id"] == "GXZM-DB03"
    assert identity["sensor_type"] == "gnss"
    assert identity["sampling_interval_seconds"] == 3600
    assert identity["schema_version"] == "1.0"
    assert identity["_payload_identity"] == {}


def test_identity_extraction_rainfall(rainfall_example):
    identity = extract_identity(rainfall_example)
    assert identity["sensor_type"] == "rainfall"
    assert "interval_minutes" in identity["_payload_identity"]


def test_identity_extraction_deep_displacement(deep_displacement_example):
    identity = extract_identity(deep_displacement_example)
    assert identity["sensor_type"] == "deep_displacement"
    assert "depth_m" in identity["_payload_identity"]


def test_identity_extraction_all_examples(any_example):
    identity = extract_identity(any_example)
    assert "project_id" in identity
    assert "sensor_id" in identity
    assert "sensor_type" in identity
    assert "sampling_interval_seconds" in identity
