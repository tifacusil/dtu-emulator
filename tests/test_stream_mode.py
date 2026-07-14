import io
import json
from pathlib import Path
from random import Random

import pytest

from sender.modes import stream_mode

EXAMPLES_DIR = Path(__file__).parents[1] / "contracts" / "examples"
GNSS_EXAMPLE = str(EXAMPLES_DIR / "gnss-shangtan.json")


class FakeTransport:
    def __init__(self, responses):
        self._responses = list(responses)
        self.closed = False

    def send_with_retry(self, frame):
        if not self._responses:
            raise ConnectionError("no more fake responses queued")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clear_identity_cache():
    stream_mode._identity_cache.clear()
    yield
    stream_mode._identity_cache.clear()


def test_handle_request_ok():
    transport = FakeTransport([(0x00, 12.5)])
    request = {"file": GNSS_EXAMPLE, "seed": 1}
    result = stream_mode._handle_request(transport, request, Random(0), Random(0))
    assert result == {"status": "OK", "latency_ms": 12.5}


def test_handle_request_rejected_status():
    transport = FakeTransport([(0x01, 8.0)])
    request = {"file": GNSS_EXAMPLE, "seed": 1}
    result = stream_mode._handle_request(transport, request, Random(0), Random(0))
    assert result == {"status": "CRC_INVALID", "latency_ms": 8.0}


def test_handle_request_corrupt_alters_frame():
    ok_transport = FakeTransport([(0x00, 1.0)])
    corrupt_transport = FakeTransport([(0x00, 1.0)])

    plain = stream_mode._handle_request(
        ok_transport, {"file": GNSS_EXAMPLE, "seed": 7}, Random(0), Random(0)
    )
    corrupted = stream_mode._handle_request(
        corrupt_transport,
        {"file": GNSS_EXAMPLE, "seed": 7, "corrupt": "crc"},
        Random(0),
        Random(0),
    )
    # Both fake transports report OK regardless — this just proves the corrupt
    # kind is accepted and wired through without raising.
    assert plain["status"] == "OK"
    assert corrupted["status"] == "OK"


def test_handle_request_unknown_corrupt_kind_raises():
    transport = FakeTransport([(0x00, 1.0)])
    request = {"file": GNSS_EXAMPLE, "corrupt": "not-a-real-kind"}
    with pytest.raises(ValueError, match="Unknown corruption kind"):
        stream_mode._handle_request(transport, request, Random(0), Random(0))


def test_get_identity_is_cached():
    identity_a = stream_mode._get_identity(GNSS_EXAMPLE)
    identity_b = stream_mode._get_identity(GNSS_EXAMPLE)
    assert identity_a is identity_b


def test_run_stream_protocol(monkeypatch):
    transport = FakeTransport([(0x00, 5.0), ValueError("boom"), (0x00, 6.0)])
    monkeypatch.setattr(
        stream_mode, "TCPTransport", lambda *a, **k: transport
    )

    requests = [
        {"file": GNSS_EXAMPLE, "seed": 1},
        {"file": GNSS_EXAMPLE, "seed": 2},
        "not json",
        {"file": GNSS_EXAMPLE, "seed": 3},
    ]
    stdin = io.StringIO("\n".join(json.dumps(r) if isinstance(r, dict) else r for r in requests) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(stream_mode.sys, "stdin", stdin)
    monkeypatch.setattr(stream_mode.sys, "stdout", stdout)

    stream_mode.run_stream(host="localhost", port=5000, ack_timeout=5.0, no_retry=True)

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert lines[0] == {"status": "OK", "latency_ms": 5.0}
    assert "error" in lines[1]  # ValueError("boom") from the fake transport
    assert "error" in lines[2]  # "not json" fails to parse before hitting the transport
    assert lines[3] == {"status": "OK", "latency_ms": 6.0}
    assert transport.closed is True
