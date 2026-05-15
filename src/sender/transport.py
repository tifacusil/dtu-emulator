"""TCP client with exponential backoff reconnection."""

import logging
import socket
import time

logger = logging.getLogger(__name__)

ACK_STATUS = {
    0x00: "OK",
    0x01: "CRC_INVALID",
    0x02: "STRUCTURE",
    0x03: "SCHEMA",
    0x04: "UNKNOWN_TYPE",
}

BACKOFF_SEQUENCE = [1, 2, 4, 8, 16, 30]


class TCPTransport:
    def __init__(
        self, host: str, port: int, ack_timeout: float = 5.0, no_retry: bool = False
    ):
        self.host = host
        self.port = port
        self.ack_timeout = ack_timeout
        self.no_retry = no_retry
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.ack_timeout)
        self._sock.connect((self.host, self.port))

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send_frame(self, frame: bytes) -> tuple[int, float]:
        """Send frame, wait for 5-byte ACK. Returns (status_byte, latency_ms)."""
        t0 = time.monotonic()
        self._sock.sendall(frame)
        ack = self._recv_exact(5)
        latency_ms = (time.monotonic() - t0) * 1000

        if ack[:2] != b"\xaa\x55" or ack[4:5] != b"\xaa":
            raise ValueError(f"Malformed ACK: {ack.hex()}")

        status = ack[2]
        return status, latency_ms

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed while reading ACK")
            buf += chunk
        return buf

    def send_with_retry(self, frame: bytes) -> tuple[int, float]:
        """Send frame with reconnection on failure. Returns (status_byte, latency_ms)."""
        backoff_idx = 0
        while True:
            try:
                if self._sock is None:
                    self.connect()
                return self.send_frame(frame)
            except (OSError, ConnectionError, socket.timeout) as exc:
                logger.error(
                    "connection lost (%s); %s",
                    exc,
                    "not retrying"
                    if self.no_retry
                    else f"retrying in {BACKOFF_SEQUENCE[min(backoff_idx, len(BACKOFF_SEQUENCE) - 1)]}s",
                )
                self.close()
                if self.no_retry:
                    raise
                delay = BACKOFF_SEQUENCE[min(backoff_idx, len(BACKOFF_SEQUENCE) - 1)]
                time.sleep(delay)
                backoff_idx += 1
                logger.info("attempting reconnect to %s:%s", self.host, self.port)
                try:
                    self.connect()
                    logger.info("connection restored")
                    return self.send_frame(frame)
                except (OSError, ConnectionError, socket.timeout) as exc2:
                    logger.error("reconnect failed: %s", exc2)
                    self.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()
