"""End-to-end in-process round-trip tests for all contract examples."""

import json
import math
from pathlib import Path

import pytest

from sender.envelope import extract_identity
from sender.frame import encode_frame, decode_frame
from sender.randomizer import build_envelope

EXAMPLES_DIR = Path(__file__).parents[1] / "contracts" / "examples"
EXAMPLE_FILES = list(EXAMPLES_DIR.glob("*.json"))


@pytest.mark.parametrize(
    "example_file", EXAMPLE_FILES, ids=[f.stem for f in EXAMPLE_FILES]
)
def test_each_example_can_be_encoded(example_file):
    with open(example_file) as f:
        envelope = json.load(f)
    frame = encode_frame(envelope)
    assert len(frame) > 6


@pytest.mark.parametrize(
    "example_file", EXAMPLE_FILES, ids=[f.stem for f in EXAMPLE_FILES]
)
def test_each_example_roundtrip_with_random(example_file):
    from random import Random

    with open(example_file) as f:
        envelope = json.load(f)

    identity = extract_identity(envelope)
    rng = Random(42)
    generated = build_envelope(identity, rng)

    frame = encode_frame(generated)
    decoded = decode_frame(frame)

    assert decoded["project_id"] == generated["project_id"]
    assert decoded["sensor_id"] == generated["sensor_id"]
    assert decoded["sensor_type"] == generated["sensor_type"]
    assert decoded["message_id"] == generated["message_id"]
    assert decoded["timestamp"] == generated["timestamp"]
    assert (
        decoded["sampling_interval_seconds"] == generated["sampling_interval_seconds"]
    )

    for k, v in generated["payload"].items():
        if isinstance(v, float):
            assert math.isclose(v, decoded["payload"][k], rel_tol=1e-6, abs_tol=1e-4), (
                f"{k}: {v} != {decoded['payload'][k]}"
            )
        else:
            assert decoded["payload"][k] == v
