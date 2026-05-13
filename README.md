# Sender — DTU Simulator (Tarjeta 2A1)

Simulates a Data Transfer Unit (DTU) from Bai et al. (2020), sending binary sensor frames over TCP to the C# Data Receiving service.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### Mode `fixture`

Generates random envelopes from a contract example and sends them.

```bash
# One frame (smoke test)
python -m sender fixture --file contracts/examples/gnss-shangtan.json

# 100 frames at 10 fps
python -m sender fixture --file contracts/examples/gnss-shangtan.json --count 100 --rate 10

# Reproducible run with seed
python -m sender fixture --file contracts/examples/gnss-shangtan.json --seed 42 --count 50

# Send corrupted frame to test C# error handling
python -m sender fixture --file contracts/examples/gnss-shangtan.json --corrupt crc

# All sensor types in parallel
for f in contracts/examples/*.json; do
  python -m sender fixture --file "$f" --count 100 --rate 5 &
done
wait
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--file PATH` | required | Contract example JSON |
| `--host` | `localhost` | C# service host |
| `--port` | `5000` | C# service port |
| `--count N` | `1` | Frames to send (`0` = infinite) |
| `--rate N` | `1.0` | Frames per second (`0` = max) |
| `--seed N` | random | Reproducibility seed |
| `--corrupt KIND` | none | Corrupt kind: `crc`, `sync_start`, `sync_end`, `length`, `version`, `type`, `schema`, `random` |
| `--corrupt-count N` | `8` | Bits to flip for `random` kind |
| `--ack-timeout SEC` | `5.0` | Seconds to wait for ACK |
| `--no-retry` | off | Disable TCP reconnection |
| `--log-level` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |

### Mode `replay`

Replays a pre-recorded scenario file.

```bash
python -m sender replay --scenario replay_scenarios/shangtan_june_2019.json

# Realtime pacing at 10× speed
python -m sender replay --scenario replay_scenarios/shangtan_june_2019.json --realtime --speedup 10
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `--scenario PATH` | required | Scenario JSON file |
| `--realtime` | off | Sleep between messages per timestamps |
| `--speedup N` | `1.0` | Accelerate realtime factor |
| `--host`, `--port`, `--ack-timeout`, `--no-retry`, `--log-level` | same as fixture | |

## Tests

```bash
pytest tests/

# With coverage
pytest tests/ --cov=sender --cov-report=term-missing
```

All 62 unit tests run without a live server.

## Contracts

`contracts/` is a static copy of the schema and example files from the Tarea 0 repo. To update after changes upstream:

```bash
CONTRACTS_REPO=~/workspace/contracts ./tools/sync_contracts.sh
```

Then commit the updated files.

## Replay scenarios

Pre-built scenarios are in `replay_scenarios/`. To regenerate from paper data:

```bash
python tools/generate_scenarios.py
```

## Binary Protocol

Frame layout: `0xAA 0x55 | VER(1) | TYPE(1) | LEN(2 BE) | PAYLOAD | CRC(2 BE) | 0x55 0xAA`

- CRC: CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF)
- Test vector: `crc16_ccitt(b"123456789") == 0x29B1`
- All multi-byte fields: big-endian

## Troubleshooting

**Connection refused:** Check `--host` and `--port`. The C# service must be running.

**ACK timeout:** Increase `--ack-timeout`. Default is 5 seconds.

**CRC mismatch on C# side:** Ensure both sides use CRC-16/CCITT-FALSE with init=0xFFFF. Run `pytest tests/test_crc.py` to verify the sender's implementation.

**Reproducibility:** Pass `--seed N` to get the same sequence across runs. Useful for debugging with the C# developer.
# dtu-emulator
