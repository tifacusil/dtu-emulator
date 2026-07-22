"""Field-realistic corpus: a fleet of sensors with physically consistent series.

`randomizer.build_envelope` draws every payload field independently per frame:
`cumulative_displacement_mm` is `uniform(0, 3000)`, so two consecutive readings
of the same sensor differ by an arbitrary amount in [-3000, +3000] mm. Fed to a
threshold engine that computes `delta / dt * 86400`, a one-second gap yields
deformation speeds up to 259,200,000 mm/day — around 13 million times the
`red` threshold — so *every* alert a load test produces is a `red` and roughly
half the evaluations alert at all. Add that the sensor identity comes from the
contract example (one `sensor_id` for the whole run) and the corpus stops
describing a monitored slope: it measures how fast the alert path runs.

This module models the fleet instead. Each sensor is a deterministic function
of its id: a quiet creep rate under the lowest alert threshold, occasional
deformation events that cross it, and a monotonically increasing cumulative
displacement — the quantity Bai et al. (2020) plot in Figure 8a. Readings are
addressed by index, and reading `i` carries the timestamp the sensor would have
stamped on its `i`-th hourly sample.

Two properties matter for the load tests that consume this:

* **Stateless.** `(sensor_id, reading_index)` fully determines the reading, so
  any worker process can serve any sensor and a respawned worker resumes the
  same series. The per-sensor caches here are memoisation, not state.
* **Compressed time, not fake time.** A load test emits thousands of frames per
  virtual hour; the virtual clock is anchored at the paper's monitoring window
  so timestamps stay in a plausible historical range instead of running years
  into the future within a single run.
"""

import hashlib
import math
import uuid
from datetime import datetime, timedelta, timezone
from random import Random

from .randomizer import generate_random_payload, random_fix_quality

# Bai et al. (2020) monitor Shangtan through June-September 2019; Figure 8a
# opens on the June 26 deformation event.
FLEET_EPOCH = datetime(2019, 6, 26, tzinfo=timezone.utc)

# The paper's Shangtan GNSS station is GXZM-DB03, so the fleet extends that
# convention. Three digits keeps ids unique up to the paper's 3,233 sensors
# without changing width below 1,000.
SENSOR_ID_TEMPLATE = "GXZM-DB{index:03d}"

# Quiet-regime creep, mm/day, drawn per sensor. Bounded below the lowest
# Shangtan threshold (blue = 10 mm/day) so a sensor outside a deformation event
# never alerts on creep alone.
CREEP_MM_DAY = (0.5, 8.0)

# Deformation events. Readings are grouped in blocks of BLOCK_READINGS (10
# virtual days at hourly sampling) and each block independently draws whether it
# contains an event, where it starts, how long it lasts and how much speed it
# adds on top of the creep. Blocking is what keeps the model O(1) per reading:
# a block's total contribution can be summed once and cached, so reading i costs
# a prefix lookup rather than a replay of i increments.
#
# The defaults put a sensor in event ~1.4% of its readings, which is the order
# of the three events the paper reports over ~2.5 months of hourly sampling.
#
# Event magnitude is drawn log-uniformly: it spans an order of magnitude and
# small events are the common case, so a uniform draw would make `red` the
# typical alert instead of the exceptional one the threshold is named for.
BLOCK_READINGS = 240
EVENT_PROBABILITY = 0.25
EVENT_DURATION_READINGS = (3, 24)
EVENT_EXCESS_MM_DAY = (4.0, 45.0)

# Starting cumulative displacement, mm. Figure 8a spans roughly 46 to 412 mm.
INITIAL_CUMULATIVE_MM = (20.0, 400.0)

# Per-component RTK carrier-phase noise, mm (1 sigma).
COMPONENT_NOISE_MM = 1.5

_SECONDS_PER_DAY = 86400.0


def sensor_id_for(index: int) -> str:
    """Name the `index`-th sensor of the fleet."""
    return SENSOR_ID_TEMPLATE.format(index=index)


def _seed(*parts: object) -> int:
    """Stable seed from arbitrary parts.

    `hash()` is salted per process, so two workers would disagree on the same
    sensor. A digest is not.
    """
    material = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(material, digest_size=8).digest(), "big")


class SensorProfile:
    """Everything about one sensor that does not change between readings.

    Derived from the sensor id alone, so every process builds the same profile.
    """

    def __init__(self, sensor_id: str, sampling_interval_seconds: int):
        rng = Random(_seed(sensor_id))
        self.sensor_id = sensor_id
        self.sampling_interval_seconds = sampling_interval_seconds
        self.day_fraction = sampling_interval_seconds / _SECONDS_PER_DAY
        self.initial_mm = rng.uniform(*INITIAL_CUMULATIVE_MM)
        self.creep_mm_day = rng.uniform(*CREEP_MM_DAY)
        self.azimuth_rad = rng.uniform(0.0, 2 * math.pi)
        self.dip_rad = rng.uniform(0.02, 0.35)
        # Sensors do not sample on the same second of the hour.
        self.clock_offset_seconds = rng.randrange(max(1, sampling_interval_seconds))
        self._events: dict[int, tuple[int, int, float] | None] = {}
        self._block_prefix_mm: list[float] = [0.0]

    def _event(self, block: int) -> tuple[int, int, float] | None:
        """(start, duration, excess_mm_day) for `block`, or None if quiet."""
        if block in self._events:
            return self._events[block]
        rng = Random(_seed(self.sensor_id, "block", block))
        event: tuple[int, int, float] | None = None
        if rng.random() < EVENT_PROBABILITY:
            low, high = EVENT_EXCESS_MM_DAY
            event = (
                rng.randrange(BLOCK_READINGS),
                rng.randint(*EVENT_DURATION_READINGS),
                low * (high / low) ** rng.random(),
            )
        self._events[block] = event
        return event

    def _event_mm_within(self, block: int, position: int) -> float:
        """Event displacement accumulated inside `block` up to local `position`."""
        event = self._event(block)
        if event is None:
            return 0.0
        start, duration, excess = event
        active = min(max(position - start + 1, 0), duration)
        return excess * active * self.day_fraction

    def _event_mm_before(self, block: int) -> float:
        """Event displacement accumulated by every block strictly before `block`."""
        while len(self._block_prefix_mm) <= block:
            done = len(self._block_prefix_mm) - 1
            self._block_prefix_mm.append(
                self._block_prefix_mm[done]
                + self._event_mm_within(done, BLOCK_READINGS - 1)
            )
        return self._block_prefix_mm[block]

    def cumulative_mm(self, reading_index: int) -> float:
        """Cumulative displacement at `reading_index`. Monotonically increasing."""
        block, position = divmod(reading_index, BLOCK_READINGS)
        creep = self.creep_mm_day * reading_index * self.day_fraction
        events = self._event_mm_before(block) + self._event_mm_within(block, position)
        return self.initial_mm + creep + events

    def speed_mm_day(self, reading_index: int) -> float:
        """Deformation speed the `reading_index`-th reading was produced at.

        Only meaningful against the immediately preceding reading; the engines
        compute their own speed from whatever baseline they hold.
        """
        block, position = divmod(reading_index, BLOCK_READINGS)
        event = self._event(block)
        excess = 0.0
        if event is not None:
            start, duration, event_excess = event
            if start <= position < start + duration:
                excess = event_excess
        return self.creep_mm_day + excess

    def timestamp(self, reading_index: int) -> datetime:
        """When the sensor took reading `reading_index`."""
        return FLEET_EPOCH + timedelta(
            seconds=self.clock_offset_seconds
            + reading_index * self.sampling_interval_seconds
        )

    def gnss_payload(self, reading_index: int, rng: Random) -> dict:
        cumulative = self.cumulative_mm(reading_index)
        horizontal = cumulative * math.cos(self.dip_rad)
        x = horizontal * math.cos(self.azimuth_rad) + rng.gauss(0.0, COMPONENT_NOISE_MM)
        y = horizontal * math.sin(self.azimuth_rad) + rng.gauss(0.0, COMPONENT_NOISE_MM)
        # Slope movement has a downward vertical component.
        z = -cumulative * math.sin(self.dip_rad) + rng.gauss(0.0, COMPONENT_NOISE_MM)
        return {
            "displacement_x_mm": x,
            "displacement_y_mm": y,
            "displacement_z_mm": z,
            "displacement_horizontal_mm": math.sqrt(x**2 + y**2),
            "cumulative_displacement_mm": cumulative,
            "fix_quality": random_fix_quality(rng),
        }


class Fleet:
    """Per-process cache of sensor profiles."""

    def __init__(self) -> None:
        self._profiles: dict[str, SensorProfile] = {}

    def profile(self, sensor_id: str, sampling_interval_seconds: int) -> SensorProfile:
        profile = self._profiles.get(sensor_id)
        if profile is None or (
            profile.sampling_interval_seconds != sampling_interval_seconds
        ):
            profile = SensorProfile(sensor_id, sampling_interval_seconds)
            self._profiles[sensor_id] = profile
        return profile

    def build_envelope(
        self, identity: dict, sensor_id: str, reading_index: int, rng: Random
    ) -> dict:
        """Envelope for one reading of one fleet sensor.

        `identity` supplies everything the fleet does not model — project,
        sensor type, sampling interval, schema version — so the contract example
        stays the source of truth for frame shape. Sensor types other than gnss
        fall back to the per-frame randomizer: the early-warning engines only
        evaluate gnss, and there is no displacement series to model for them.
        """
        interval = identity["sampling_interval_seconds"]
        profile = self.profile(sensor_id, interval)
        sensor_type = identity["sensor_type"]
        if sensor_type == "gnss":
            payload = profile.gnss_payload(reading_index, rng)
        else:
            payload = generate_random_payload(
                sensor_type, identity.get("_payload_identity", {}), rng
            )
        return {
            "schema_version": identity.get("schema_version", "1.0"),
            "message_id": str(uuid.uuid4()),
            "project_id": identity["project_id"],
            "sensor_id": sensor_id,
            "sensor_type": sensor_type,
            "timestamp": profile.timestamp(reading_index).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "sampling_interval_seconds": interval,
            "payload": payload,
        }
