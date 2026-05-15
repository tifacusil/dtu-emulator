import struct

import pytest

from sender.corruption import corrupt_frame
from sender.crc import crc16_ccitt
from sender.frame import encode_frame, decode_frame, SYNC_START, SYNC_END


def _make_gnss_frame(gnss_example):
    return encode_frame(gnss_example)


def test_crc_corruption(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "crc")
    # Frame must otherwise be structurally OK but CRC must differ
    assert corrupted[:2] == SYNC_START
    assert corrupted[-2:] == SYNC_END
    crc_in_frame = struct.unpack_from(">H", corrupted, -4)[0]
    crc_computed = crc16_ccitt(bytes(corrupted[2:-4]))
    assert crc_in_frame != crc_computed
    with pytest.raises(ValueError, match="CRC"):
        decode_frame(corrupted)


def test_sync_start_corruption(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "sync_start")
    assert corrupted[:2] == b"\x00\x00"
    with pytest.raises(ValueError, match="sync_start"):
        decode_frame(corrupted)


def test_sync_end_corruption(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "sync_end")
    assert corrupted[-2:] == b"\x00\x00"
    with pytest.raises(ValueError, match="sync_end"):
        decode_frame(corrupted)


def test_length_corruption(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "length")
    with pytest.raises(ValueError):
        decode_frame(corrupted)


def test_version_corruption(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "version")
    with pytest.raises(ValueError, match="version"):
        decode_frame(corrupted)


def test_type_corruption(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "type")
    # Type byte should be 0xFF
    assert corrupted[3] == 0xFF
    with pytest.raises(ValueError, match="type"):
        decode_frame(corrupted)


def test_schema_corruption_keeps_valid_structure(gnss_example):
    frame = _make_gnss_frame(gnss_example)
    corrupted = corrupt_frame(frame, "schema")
    # Frame should decode structurally (CRC is recomputed in corruption)
    decoded = decode_frame(corrupted)
    # displacement_horizontal_mm must be negative (schema violation)
    assert decoded["payload"]["displacement_horizontal_mm"] < 0


def test_random_corruption(gnss_example):
    from random import Random

    frame = _make_gnss_frame(gnss_example)
    rng = Random(42)
    corrupted = corrupt_frame(frame, "random", random_count=8, rng=rng)
    # sync bytes must be intact
    assert corrupted[:2] == SYNC_START
    assert corrupted[-2:] == SYNC_END
    # Frame must differ from original
    assert corrupted != frame


def test_each_kind(gnss_example):
    kinds = ["crc", "sync_start", "sync_end", "length", "version", "type"]
    frame = _make_gnss_frame(gnss_example)
    for kind in kinds:
        from random import Random

        corrupted = corrupt_frame(frame, kind, rng=Random(0))
        with pytest.raises((ValueError, Exception)):
            decode_frame(corrupted)
