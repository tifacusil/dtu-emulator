import math
import struct

import pytest

from sender.frame import encode_frame, decode_frame, SYNC_START, SYNC_END


def _compare_payloads(a: dict, b: dict):
    for k in a:
        if isinstance(a[k], float):
            assert math.isclose(a[k], b[k], rel_tol=1e-6, abs_tol=1e-4), f"{k}: {a[k]} != {b[k]}"
        else:
            assert a[k] == b[k], f"{k}: {a[k]} != {b[k]}"


def test_roundtrip(gnss_example):
    frame = encode_frame(gnss_example)
    decoded = decode_frame(frame)
    assert decoded["project_id"] == gnss_example["project_id"]
    assert decoded["sensor_id"] == gnss_example["sensor_id"]
    assert decoded["sensor_type"] == gnss_example["sensor_type"]
    assert decoded["sampling_interval_seconds"] == gnss_example["sampling_interval_seconds"]
    _compare_payloads(gnss_example["payload"], decoded["payload"])


def test_sync_bytes(gnss_example):
    frame = encode_frame(gnss_example)
    assert frame[:2] == SYNC_START
    assert frame[-2:] == SYNC_END


def test_size_field(gnss_example):
    frame = encode_frame(gnss_example)
    declared_len = struct.unpack_from(">H", frame, 4)[0]
    actual_payload = frame[6 : 6 + declared_len]
    assert len(actual_payload) == declared_len


def test_bad_sync_start_raises(gnss_example):
    frame = bytearray(encode_frame(gnss_example))
    frame[0] = 0x00
    with pytest.raises(ValueError, match="sync_start"):
        decode_frame(bytes(frame))


def test_bad_sync_end_raises(gnss_example):
    frame = bytearray(encode_frame(gnss_example))
    frame[-1] = 0x00
    with pytest.raises(ValueError, match="sync_end"):
        decode_frame(bytes(frame))


def test_bad_crc_raises(gnss_example):
    frame = bytearray(encode_frame(gnss_example))
    frame[-4] ^= 0xFF
    with pytest.raises(ValueError, match="CRC"):
        decode_frame(bytes(frame))


def test_unknown_version_raises(gnss_example):
    frame = bytearray(encode_frame(gnss_example))
    frame[2] = 0xFF
    with pytest.raises(ValueError, match="version"):
        decode_frame(bytes(frame))
