"""Frame corruption helpers for testing the C# parser's error handling."""

import struct


def corrupt_frame(frame: bytes, kind: str, random_count: int = 8, rng=None) -> bytes:
    frame = bytearray(frame)

    if kind == "crc":
        # XOR the 2 CRC bytes (at positions -4 and -3, before 0x55 0xAA)
        frame[-4] ^= 0xFF
        frame[-3] ^= 0xFF

    elif kind == "sync_start":
        frame[0] = 0x00
        frame[1] = 0x00

    elif kind == "sync_end":
        frame[-2] = 0x00
        frame[-1] = 0x00

    elif kind == "length":
        original = struct.unpack_from(">H", frame, 4)[0]
        struct.pack_into(">H", frame, 4, original + 5)

    elif kind == "version":
        frame[2] = 0xFF

    elif kind == "type":
        frame[3] = 0xFF

    elif kind == "schema":
        # Inject a negative displacement_horizontal_mm value into a GNSS frame.
        # Header starts at offset 6; payload sensor data starts after header.
        # displacement_horizontal_mm is at bytes 12..15 of the sensor payload.
        # We need to locate where the sensor payload begins.
        # Header: 16(uuid) + 1 + proj_len + 1 + sens_len + 8 + 4
        proj_len = frame[6 + 16]
        sens_len = frame[6 + 16 + 1 + proj_len]
        sensor_payload_start = 6 + 16 + 1 + proj_len + 1 + sens_len + 8 + 4
        # displacement_horizontal_mm is at offset 12 (3rd float32) in gnss sensor payload
        h_offset = sensor_payload_start + 12
        struct.pack_into(">f", frame, h_offset, -1.5)
        # Recompute CRC over VER+TYPE+LEN+PAYLOAD
        from .crc import crc16_ccitt
        crc_input = bytes(frame[2:-4])
        new_crc = crc16_ccitt(crc_input)
        struct.pack_into(">H", frame, -4, new_crc)

    elif kind == "random":
        if rng is None:
            import random
            rng = random
        # Flip bits only in the payload region (skip sync_start=2, ver=1, type=1, len=2, crc=2, sync_end=2)
        payload_start = 6
        payload_end = len(frame) - 4  # before CRC+SYNC_END
        payload_len = payload_end - payload_start
        for _ in range(random_count):
            byte_idx = payload_start + rng.randint(0, payload_len - 1)
            bit_idx = rng.randint(0, 7)
            frame[byte_idx] ^= (1 << bit_idx)

    else:
        raise ValueError(f"Unknown corruption kind: {kind}")

    return bytes(frame)
