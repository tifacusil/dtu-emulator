"""Binary encode/decode for each sensor payload type."""

import struct

TYPE_CODES = {
    "gnss": 0x01,
    "rainfall": 0x02,
    "strain": 0x03,
    "soil_pressure": 0x04,
    "deep_displacement": 0x05,
}

TYPE_NAMES = {v: k for k, v in TYPE_CODES.items()}

FIX_QUALITY_ENC = {
    "no_fix": 0x00,
    "single": 0x01,
    "dgps": 0x02,
    "rtk_float": 0x03,
    "rtk_fixed": 0x04,
}

FIX_QUALITY_DEC = {v: k for k, v in FIX_QUALITY_ENC.items()}


def encode_payload(sensor_type: str, payload: dict) -> bytes:
    if sensor_type == "gnss":
        return _encode_gnss(payload)
    elif sensor_type == "rainfall":
        return _encode_rainfall(payload)
    elif sensor_type == "strain":
        return _encode_strain(payload)
    elif sensor_type == "soil_pressure":
        return _encode_soil_pressure(payload)
    elif sensor_type == "deep_displacement":
        return _encode_deep_displacement(payload)
    raise ValueError(f"Unknown sensor_type: {sensor_type}")


def decode_payload(sensor_type: str, data: bytes) -> dict:
    if sensor_type == "gnss":
        return _decode_gnss(data)
    elif sensor_type == "rainfall":
        return _decode_rainfall(data)
    elif sensor_type == "strain":
        return _decode_strain(data)
    elif sensor_type == "soil_pressure":
        return _decode_soil_pressure(data)
    elif sensor_type == "deep_displacement":
        return _decode_deep_displacement(data)
    raise ValueError(f"Unknown sensor_type: {sensor_type}")


def _encode_gnss(p: dict) -> bytes:
    return struct.pack(
        ">fffffB",
        p["displacement_x_mm"],
        p["displacement_y_mm"],
        p["displacement_z_mm"],
        p["displacement_horizontal_mm"],
        p["cumulative_displacement_mm"],
        FIX_QUALITY_ENC[p["fix_quality"]],
    )


def _decode_gnss(data: bytes) -> dict:
    x, y, z, h, cumul = struct.unpack_from(">fffff", data, 0)
    fix_byte = data[20]
    return {
        "displacement_x_mm": x,
        "displacement_y_mm": y,
        "displacement_z_mm": z,
        "displacement_horizontal_mm": h,
        "cumulative_displacement_mm": cumul,
        "fix_quality": FIX_QUALITY_DEC[fix_byte],
    }


def _encode_rainfall(p: dict) -> bytes:
    return struct.pack(">ffH", p["rainfall_mm"], p["cumulative_rainfall_mm"], p["interval_minutes"])


def _decode_rainfall(data: bytes) -> dict:
    rain, cumul = struct.unpack_from(">ff", data, 0)
    interval = struct.unpack_from(">H", data, 8)[0]
    return {
        "rainfall_mm": rain,
        "cumulative_rainfall_mm": cumul,
        "interval_minutes": interval,
    }


def _encode_strain(p: dict) -> bytes:
    has_temp = "temperature_celsius" in p
    base = struct.pack(">Bf", 0x01 if has_temp else 0x00, p["strain_microstrain"])
    if has_temp:
        base += struct.pack(">f", p["temperature_celsius"])
    return base


def _decode_strain(data: bytes) -> dict:
    has_temp = data[0] == 0x01
    strain = struct.unpack_from(">f", data, 1)[0]
    result = {"strain_microstrain": strain}
    if has_temp:
        temp = struct.unpack_from(">f", data, 5)[0]
        result["temperature_celsius"] = temp
    return result


def _encode_soil_pressure(p: dict) -> bytes:
    has_temp = "temperature_celsius" in p
    base = struct.pack(">Bf", 0x01 if has_temp else 0x00, p["pressure_kpa"])
    if has_temp:
        base += struct.pack(">f", p["temperature_celsius"])
    return base


def _decode_soil_pressure(data: bytes) -> dict:
    has_temp = data[0] == 0x01
    pressure = struct.unpack_from(">f", data, 1)[0]
    result = {"pressure_kpa": pressure}
    if has_temp:
        temp = struct.unpack_from(">f", data, 5)[0]
        result["temperature_celsius"] = temp
    return result


def _encode_deep_displacement(p: dict) -> bytes:
    return struct.pack(">ffff", p["depth_m"], p["tilt_x_mm"], p["tilt_y_mm"], p["cumulative_tilt_mm"])


def _decode_deep_displacement(data: bytes) -> dict:
    depth, tilt_x, tilt_y, cumul = struct.unpack_from(">ffff", data, 0)
    return {
        "depth_m": depth,
        "tilt_x_mm": tilt_x,
        "tilt_y_mm": tilt_y,
        "cumulative_tilt_mm": cumul,
    }
