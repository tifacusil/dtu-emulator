"""Serialization/deserialization of the common header shared by all sensor types."""

import struct
import uuid
from datetime import datetime, timezone


IDENTITY_FIELDS_BASE = {"project_id", "sensor_id", "sensor_type", "sampling_interval_seconds", "schema_version"}

PAYLOAD_IDENTITY_FIELDS = {
    "rainfall": {"interval_minutes"},
    "deep_displacement": {"depth_m"},
    "gnss": set(),
    "strain": set(),
    "soil_pressure": set(),
}


def encode_header(envelope: dict) -> bytes:
    msg_id = uuid.UUID(envelope["message_id"]).bytes  # 16 bytes

    proj = envelope["project_id"].encode("ascii")
    sens = envelope["sensor_id"].encode("ascii")

    ts_str = envelope["timestamp"]
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    ts_ms = int(dt.timestamp() * 1000)

    sampling = envelope["sampling_interval_seconds"]

    return (
        msg_id
        + struct.pack("B", len(proj))
        + proj
        + struct.pack("B", len(sens))
        + sens
        + struct.pack(">q", ts_ms)
        + struct.pack(">I", sampling)
    )


def decode_header(data: bytes, offset: int = 0) -> tuple[dict, int]:
    msg_id = uuid.UUID(bytes=data[offset : offset + 16])
    offset += 16

    proj_len = data[offset]
    offset += 1
    project_id = data[offset : offset + proj_len].decode("ascii")
    offset += proj_len

    sens_len = data[offset]
    offset += 1
    sensor_id = data[offset : offset + sens_len].decode("ascii")
    offset += sens_len

    ts_ms = struct.unpack_from(">q", data, offset)[0]
    offset += 8
    timestamp = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sampling = struct.unpack_from(">I", data, offset)[0]
    offset += 4

    header = {
        "message_id": str(msg_id),
        "project_id": project_id,
        "sensor_id": sensor_id,
        "timestamp": timestamp,
        "sampling_interval_seconds": sampling,
    }
    return header, offset


def extract_identity(envelope: dict) -> dict:
    identity = {k: envelope[k] for k in IDENTITY_FIELDS_BASE if k in envelope}
    payload_id_keys = PAYLOAD_IDENTITY_FIELDS.get(envelope["sensor_type"], set())
    if payload_id_keys:
        identity["_payload_identity"] = {k: envelope["payload"][k] for k in payload_id_keys if k in envelope["payload"]}
    else:
        identity["_payload_identity"] = {}
    return identity
