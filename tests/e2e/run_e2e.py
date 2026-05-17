#!/usr/bin/env python3
"""End-to-end test orchestrator: sender → C# Data Receiving → Redis → RabbitMQ."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import redis as redis_lib
import requests
import yaml

ROOT = Path(__file__).parents[2]
FIXTURES_DIR = ROOT / "contracts" / "examples"
RESULTS_DIR = Path(__file__).parent / "results"

ROUTING_KEYS = {
    "gnss-shangtan.json": "sensors.shangtan.gnss",
    "rainfall-shangtan.json": "sensors.shangtan.rainfall",
    "strain-shangtan.json": "sensors.shangtan.strain",
    "soil-pressure-shangtan.json": "sensors.shangtan.soil_pressure",
    "deep-displacement-lingzhan.json": "sensors.lingzhan.deep_displacement",
}


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    config_file = Path(__file__).parent / "config.yaml"
    with open(config_file) as f:
        cfg = yaml.safe_load(f)

    dr = cfg["data_receiving"]
    dr["host"] = os.environ.get("DR_HOST", dr["host"])
    dr["tcp_port"] = int(os.environ.get("DR_TCP_PORT", dr["tcp_port"]))
    dr["health_port"] = int(os.environ.get("DR_HEALTH_PORT", dr["health_port"]))

    rmq = cfg["rabbitmq"]
    rmq["host"] = os.environ.get("RABBITMQ_HOST", rmq["host"])
    rmq["port"] = int(os.environ.get("RABBITMQ_PORT", rmq["port"]))
    rmq["username"] = os.environ.get("RABBITMQ_USER", rmq["username"])
    rmq["password"] = os.environ.get("RABBITMQ_PASSWORD", rmq["password"])

    r = cfg["redis"]
    r["host"] = os.environ.get("REDIS_HOST", r["host"])
    r["port"] = int(os.environ.get("REDIS_PORT", r["port"]))
    r["password"] = os.environ.get("REDIS_PASSWORD", r.get("password"))

    c = cfg["consul"]
    c["host"] = os.environ.get("CONSUL_HOST", c["host"])
    c["port"] = int(os.environ.get("CONSUL_PORT", c["port"]))
    c["token"] = os.environ.get("CONSUL_TOKEN", c.get("token"))

    return cfg


# ── Sender invocation ─────────────────────────────────────────────────────────

def run_sender(cfg: dict, fixture_file: Path, count: int = 1,
               corrupt: str | None = None,
               no_retry: bool = True) -> subprocess.CompletedProcess:
    dr = cfg["data_receiving"]
    cmd = [
        sys.executable, "-m", "sender", "fixture",
        "--file", str(fixture_file),
        "--count", str(count),
        "--host", dr["host"],
        "--port", str(dr["tcp_port"]),
        "--ack-timeout", str(cfg["sender"]["timeout_ack"]),
        "--log-level", "WARNING",
    ]
    if no_retry:
        cmd += ["--no-retry"]
    if corrupt:
        cmd += ["--corrupt", corrupt]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)


# ── RabbitMQ helpers ──────────────────────────────────────────────────────────

def rmq_queue_count(cfg: dict) -> int:
    rmq = cfg["rabbitmq"]
    url = (f"http://{rmq['host']}:{rmq['management_port']}"
           f"/api/queues/%2F/{rmq['queue']}")
    resp = requests.get(url, auth=(rmq["username"], rmq["password"]), timeout=5)
    resp.raise_for_status()
    return resp.json().get("messages", 0)


def rmq_peek_routing_keys(cfg: dict, n: int = 10) -> list[str] | None:
    """Peek up to n messages via Management API (requeue=true). Return routing keys,
    or None if the user lacks management permissions (non-fatal)."""
    rmq = cfg["rabbitmq"]
    url = (f"http://{rmq['host']}:{rmq['management_port']}"
           f"/api/queues/%2F/{rmq['queue']}/get")
    payload = {"count": n, "requeue": True, "encoding": "auto",
               "ackmode": "ack_requeue_true"}
    resp = requests.post(url, json=payload,
                         auth=(rmq["username"], rmq["password"]), timeout=5)
    if resp.status_code == 401:
        return None  # publish-only user; skip routing key check
    resp.raise_for_status()
    return [msg["routing_key"] for msg in resp.json()]


# ── Redis helper ──────────────────────────────────────────────────────────────

def redis_client(cfg: dict) -> redis_lib.Redis:
    r = cfg["redis"]
    return redis_lib.Redis(
        host=r["host"], port=r["port"],
        password=r.get("password") or None,
        decode_responses=True,
        socket_timeout=5,
    )


def redis_sensor_buffer_count(cfg: dict) -> int:
    try:
        return len(redis_client(cfg).keys("sensor_buffer:*"))
    except redis_lib.RedisError:
        return -1


# ── Poll helper ───────────────────────────────────────────────────────────────

def poll_until(condition_fn, timeout: float, interval: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


# ── Test result bookkeeping ───────────────────────────────────────────────────

class Result:
    def __init__(self, test_id: str, name: str):
        self.id = test_id
        self.name = name
        self.status = "PASS"
        self.duration = 0.0
        self.detail: str | None = None
        self.hint: str | None = None

    def fail(self, detail: str, hint: str | None = None):
        self.status = "FAIL"
        self.detail = detail
        self.hint = hint

    def skip(self, reason: str):
        self.status = "SKIP"
        self.detail = reason


# ── Tests ─────────────────────────────────────────────────────────────────────

def t01_health_check(cfg: dict) -> Result:
    r = Result("T-01", "Health check")
    t0 = time.monotonic()
    try:
        dr = cfg["data_receiving"]
        url = f"http://{dr['host']}:{dr['health_port']}/health"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            r.fail(f"HTTP {resp.status_code} (expected 200)", "Is the C# service running?")
        else:
            body = resp.json()
            if body.get("status") != "ok":
                r.fail(f"status={body.get('status')!r} (expected 'ok')")
    except requests.RequestException as exc:
        r.fail(f"Connection error: {exc}", "Is the C# service reachable?")
    r.duration = time.monotonic() - t0
    return r


def t02_consul_registration(cfg: dict) -> Result:
    r = Result("T-02", "Consul registration")
    t0 = time.monotonic()
    try:
        c = cfg["consul"]
        url = f"http://{c['host']}:{c['port']}/v1/health/service/data-receiving"
        headers = {"X-Consul-Token": c["token"]} if c.get("token") else {}
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
        instances = resp.json()
        if not instances:
            r.fail("No instances of 'data-receiving' found in Consul")
        else:
            passing = [i for i in instances
                       if i.get("Checks") and
                       all(ch["Status"] == "passing" for ch in i["Checks"])]
            if not passing:
                statuses = [ch["Status"] for i in instances for ch in i.get("Checks", [])]
                r.fail(f"No passing instances; statuses: {statuses}")
    except requests.RequestException as exc:
        r.fail(f"Connection error: {exc}", "Is Consul reachable and token correct?")
    r.duration = time.monotonic() - t0
    return r


def t03_round_trip(cfg: dict, fixture_name: str) -> Result:
    sensor_label = fixture_name.replace(".json", "").replace("-shangtan", "").replace("-lingzhan", "")
    r = Result("T-03", f"Round-trip: {sensor_label}")
    t0 = time.monotonic()

    expected_key = ROUTING_KEYS[fixture_name]
    fixture_path = FIXTURES_DIR / fixture_name

    try:
        count_before = rmq_queue_count(cfg)
    except Exception as exc:
        r.fail(f"Cannot read queue count: {exc}")
        r.duration = time.monotonic() - t0
        return r

    proc = run_sender(cfg, fixture_path, count=1)
    if proc.returncode != 0:
        r.fail(f"Sender exited {proc.returncode}: {proc.stderr[:200]}")
        r.duration = time.monotonic() - t0
        return r

    # Poll for queue count to increase (up to 10s)
    reached = poll_until(
        lambda: rmq_queue_count(cfg) > count_before,
        timeout=10.0,
    )
    if not reached:
        r.fail(
            f"Queue '{cfg['rabbitmq']['queue']}' count did not increase after 10s timeout",
            f"check OutputMode=rabbitmq in service appsettings.json; expected routing_key={expected_key}",
        )
        r.duration = time.monotonic() - t0
        return r

    # Verify routing key by peeking queue (best-effort — requires management permissions)
    try:
        keys_seen = rmq_peek_routing_keys(cfg, n=20)
        if keys_seen is None:
            pass  # publish-only user; count increase is sufficient evidence
        elif expected_key not in keys_seen:
            r.fail(
                f"Routing key '{expected_key}' not found in queue; saw: {keys_seen}",
                "Check the service exchange binding configuration",
            )
    except Exception as exc:
        r.fail(f"RabbitMQ peek failed: {exc}")
        r.duration = time.monotonic() - t0
        return r

    # Redis: no leftover sensor_buffer:* keys
    buf_count = redis_sensor_buffer_count(cfg)
    if buf_count > 0:
        r.fail(f"Redis still has {buf_count} sensor_buffer:* keys after flush")

    r.duration = time.monotonic() - t0
    return r


def t04_corrupt_frame(cfg: dict) -> Result:
    r = Result("T-04", "Corrupt frame → pipeline continues")
    t0 = time.monotonic()

    fixture_path = FIXTURES_DIR / "gnss-shangtan.json"

    # Send corrupt frame
    proc = run_sender(cfg, fixture_path, count=1, corrupt="crc")
    if proc.returncode != 0:
        # Non-zero exit is expected when service rejects the frame; that's OK
        pass

    time.sleep(2.0)

    # Now send a valid frame and verify the pipeline still works
    try:
        count_before = rmq_queue_count(cfg)
    except Exception as exc:
        r.fail(f"Cannot read queue count after corrupt frame: {exc}")
        r.duration = time.monotonic() - t0
        return r

    # Allow retry so reconnect works if the service closed the connection
    proc2 = run_sender(cfg, fixture_path, count=1, no_retry=False)
    if proc2.returncode != 0:
        r.fail(f"Valid frame after corrupt failed, sender exit {proc2.returncode}: {proc2.stderr[:200]}")
        r.duration = time.monotonic() - t0
        return r

    reached = poll_until(
        lambda: rmq_queue_count(cfg) > count_before,
        timeout=10.0,
    )
    if not reached:
        r.fail(
            "Valid frame after corrupt did not reach queue — pipeline may be broken",
            "Check if service drops connection after CRC error instead of staying alive",
        )

    r.duration = time.monotonic() - t0
    return r


def t05_volume(cfg: dict) -> Result:
    r = Result("T-05", "Volume: 50 frames, 0 lost")
    t0 = time.monotonic()

    fixture_path = FIXTURES_DIR / "gnss-shangtan.json"
    frame_count = 50

    try:
        count_before = rmq_queue_count(cfg)
    except Exception as exc:
        r.fail(f"Cannot read initial queue count: {exc}")
        r.duration = time.monotonic() - t0
        return r

    proc = run_sender(cfg, fixture_path, count=frame_count)
    if proc.returncode != 0:
        r.fail(f"Sender exited {proc.returncode}: {proc.stderr[:200]}")
        r.duration = time.monotonic() - t0
        return r

    reached = poll_until(
        lambda: rmq_queue_count(cfg) >= count_before + frame_count,
        timeout=10.0,
        interval=0.5,
    )

    count_after = rmq_queue_count(cfg)
    delta = count_after - count_before

    if not reached or delta < frame_count:
        r.fail(
            f"Expected +{frame_count} messages in queue, got +{delta} (before={count_before}, after={count_after})",
            "Some frames may have been dropped or rejected; check service logs",
        )
        r.duration = time.monotonic() - t0
        return r

    buf_count = redis_sensor_buffer_count(cfg)
    if buf_count > 0:
        r.fail(f"Redis still has {buf_count} sensor_buffer:* keys after 50-frame flush")

    r.duration = time.monotonic() - t0
    return r


# ── Report ────────────────────────────────────────────────────────────────────

STATUS_ICON = {"PASS": "✓ PASS", "FAIL": "✗ FAIL", "SKIP": "- SKIP"}


def print_report(cfg: dict, results: list[Result], total_seconds: float,
                 sender_info: dict) -> None:
    dr = cfg["data_receiving"]
    rmq = cfg["rabbitmq"]
    r = cfg["redis"]
    c = cfg["consul"]

    passed = sum(1 for x in results if x.status == "PASS")
    failed = sum(1 for x in results if x.status == "FAIL")
    skipped = sum(1 for x in results if x.status == "SKIP")

    modes_str = ", ".join(sender_info["modes_found"])
    corrupt_str = "sí" if sender_info["corrupt_flag_available"] else "no"
    run_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print()
    print("═" * 55)
    print("  Landslide Monitoring — End-to-End Test")
    print("  Data Receiving (2A1 + 2A2 + 2A3)")
    print("  Bai et al. (2020) — Shangtan & Lingzhan")
    print("═" * 55)
    print()
    print(f"  Target:   {dr['host']}:{dr['tcp_port']} (TCP) | :{dr['health_port']} (HTTP)")
    print(f"  RabbitMQ: {rmq['host']}:{rmq['port']}")
    print(f"  Redis:    {r['host']}:{r['port']}")
    print(f"  Consul:   {c['host']}:{c['port']}")
    print(f"  Sender:   modes={modes_str}, corrupt={corrupt_str}")
    print(f"  Run at:   {run_at}")
    print()
    print("─" * 55)

    for res in results:
        icon = STATUS_ICON[res.status]
        name_padded = res.name.ljust(38)
        print(f"  {res.id}  {name_padded} {icon}  ({res.duration:.2f}s)")
        if res.status == "FAIL":
            print(f"        {res.detail}")
            if res.hint:
                print(f"        Hint: {res.hint}")
        elif res.status == "SKIP":
            print(f"        {res.detail}")

    print("─" * 55)
    print(f"  PASSED: {passed}   FAILED: {failed}   SKIPPED: {skipped}")
    print()

    if failed == 0:
        print("  2A1+2A2+2A3 gate: ✓ READY FOR 2A4")
    else:
        print("  2A1+2A2+2A3 gate: ✗ NOT READY — fix failing tests")

    print("═" * 55)
    print()


def write_json_report(cfg: dict, results: list[Result], total_seconds: float,
                      sender_info: dict) -> Path:
    dr = cfg["data_receiving"]
    run_id = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp_file = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    passed = sum(1 for x in results if x.status == "PASS")
    failed = sum(1 for x in results if x.status == "FAIL")
    skipped = sum(1 for x in results if x.status == "SKIP")

    report = {
        "run_id": run_id,
        "target": {
            "host": dr["host"],
            "tcp_port": dr["tcp_port"],
            "health_port": dr["health_port"],
        },
        "sender_info": sender_info,
        "summary": {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total_seconds": round(total_seconds, 2),
        },
        "tests": [
            {
                "id": res.id,
                "name": res.name,
                "status": res.status,
                "duration_seconds": round(res.duration, 3),
                "detail": res.detail,
            }
            for res in results
        ],
    }

    out_path = RESULTS_DIR / f"run_{timestamp_file}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    cfg = load_config()
    results: list[Result] = []
    t_global = time.monotonic()

    sender_info = {
        "modes_found": ["fixture", "replay"],
        "corrupt_flag_available": True,
        "corrupt_values": ["crc", "sync_start", "sync_end", "length",
                           "version", "type", "schema", "random"],
        "fixtures_found": sorted(ROUTING_KEYS.keys()),
    }

    # T-01 — must pass or abort
    r01 = t01_health_check(cfg)
    results.append(r01)
    if r01.status == "FAIL":
        print_report(cfg, results, time.monotonic() - t_global, sender_info)
        print("  ABORTED: health check failed — no point running further tests.")
        return 1

    # T-02
    results.append(t02_consul_registration(cfg))

    # T-03 — one per fixture, in deterministic order
    for fixture_name in sorted(ROUTING_KEYS.keys()):
        results.append(t03_round_trip(cfg, fixture_name))

    # T-04
    results.append(t04_corrupt_frame(cfg))

    # T-05
    results.append(t05_volume(cfg))

    total = time.monotonic() - t_global
    print_report(cfg, results, total, sender_info)

    out = write_json_report(cfg, results, total, sender_info)
    print(f"  Results saved to: {out.relative_to(ROOT)}")
    print()

    failed = sum(1 for r in results if r.status == "FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
