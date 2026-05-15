"""Binary frame encoder/decoder.

Frame layout:
  0xAA 0x55 | VER(1) | TYPE(1) | LEN(2 BE) | PAYLOAD | CRC(2 BE) | 0x55 0xAA
CRC covers: VER + TYPE + LEN + PAYLOAD
"""

import struct

from .crc import crc16_ccitt
from .envelope import encode_header, decode_header
from .payloads import TYPE_CODES, TYPE_NAMES, encode_payload, decode_payload

SYNC_START = b"\xaa\x55"
SYNC_END = b"\x55\xaa"
PROTOCOL_VERSION = 0x01


def encode_frame(envelope: dict) -> bytes:
    sensor_type = envelope["sensor_type"]
    type_byte = TYPE_CODES[sensor_type]

    header_bytes = encode_header(envelope)
    payload_bytes = encode_payload(sensor_type, envelope["payload"])
    full_payload = header_bytes + payload_bytes

    length = len(full_payload)
    ver_type_len = struct.pack(">BBH", PROTOCOL_VERSION, type_byte, length)
    crc_input = ver_type_len + full_payload
    crc = crc16_ccitt(crc_input)

    return SYNC_START + crc_input + struct.pack(">H", crc) + SYNC_END


def decode_frame(data: bytes) -> dict:
    if data[:2] != SYNC_START:
        raise ValueError(f"Bad sync_start: {data[:2].hex()}")
    if data[-2:] != SYNC_END:
        raise ValueError(f"Bad sync_end: {data[-2:].hex()}")

    version = data[2]
    if version != PROTOCOL_VERSION:
        raise ValueError(f"Unknown protocol version: {version:#04x}")

    type_byte = data[3]
    if type_byte not in TYPE_NAMES:
        raise ValueError(f"Unknown type byte: {type_byte:#04x}")

    length = struct.unpack_from(">H", data, 4)[0]
    payload_start = 6
    payload_end = payload_start + length

    if len(data) != payload_end + 2 + 2:  # +2 CRC +2 sync_end
        raise ValueError(
            f"Frame length mismatch: declared {length}, actual {len(data)}"
        )

    crc_data = data[2:payload_end]
    received_crc = struct.unpack_from(">H", data, payload_end)[0]
    expected_crc = crc16_ccitt(crc_data)
    if received_crc != expected_crc:
        raise ValueError(
            f"CRC mismatch: got {received_crc:#06x}, expected {expected_crc:#06x}"
        )

    full_payload = data[payload_start:payload_end]
    sensor_type = TYPE_NAMES[type_byte]

    header, header_end = decode_header(full_payload, 0)
    sensor_payload = decode_payload(sensor_type, full_payload[header_end:])

    return {
        "schema_version": "1.0",
        "message_id": header["message_id"],
        "project_id": header["project_id"],
        "sensor_id": header["sensor_id"],
        "sensor_type": sensor_type,
        "timestamp": header["timestamp"],
        "sampling_interval_seconds": header["sampling_interval_seconds"],
        "payload": sensor_payload,
    }
