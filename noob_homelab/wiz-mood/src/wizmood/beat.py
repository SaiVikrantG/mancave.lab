import asyncio
import logging
import math
import time

from wizmood.bulb import Bulb

log = logging.getLogger("wizmood.beat")

MIN_BPM = 60.0
MAX_BPM = 180.0

TICK_HZ = 20
TICK_PERIOD = 1.0 / TICK_HZ

# Fraction of each beat period over which the pulse decays. 0.3 means the
# decay is ~95% done in the first third of the beat, giving a clear "hit then
# settle" feel instead of a smooth sine.
DECAY_FRACTION = 0.3

# Don't push a new setPilot unless the brightness differs from last-sent by
# at least this much — keeps calm songs quiet on the wire.
BRIGHTNESS_DEADZONE = 3


def _clamp_bpm(bpm: float) -> float:
    while bpm > MAX_BPM:
        bpm /= 2
    while bpm < MIN_BPM:
        bpm *= 2
    return bpm


class BeatEngine:
    def __init__(self, bulb: Bulb) -> None:
        self._bulb = bulb
        self._rgb: tuple[int, int, int] = (0, 0, 0)
        self._bright_high: int = 0
        self._bright_low: int = 0
        self._bpm: float = 0.0
        self._anchor_song_ms: float = 0.0
        self._anchor_wall: float = 0.0
        self._enabled = False
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._last_sent_brightness: int = -1

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def update(
        self,
        rgb: tuple[int, int, int],
        bright_high: int,
        bright_low: int,
        bpm: float,
        progress_ms: int,
    ) -> None:
        rgb_changed = rgb != self._rgb
        self._rgb = rgb
        self._bright_high = bright_high
        self._bright_low = max(10, bright_low)
        self._bpm = _clamp_bpm(bpm) if bpm > 0 else 0.0
        self._anchor_song_ms = float(progress_ms)
        self._anchor_wall = time.monotonic()
        self._enabled = self._bpm > 0
        if rgb_changed:
            # Force a resend so the color actually changes on track change,
            # even if the brightness stays similar.
            self._last_sent_brightness = -1
        self._wake.set()

    def disable(self) -> None:
        self._enabled = False
        self._last_sent_brightness = -1
        self._wake.set()

    def _current_song_ms(self) -> float:
        return self._anchor_song_ms + (time.monotonic() - self._anchor_wall) * 1000.0

    def _envelope(self) -> float:
        """Returns a 0..1 pulse value: 1 at beat edge, decays toward 0."""
        beat_period_ms = 60000.0 / self._bpm
        song_ms = self._current_song_ms()
        t_since_beat_ms = song_ms % beat_period_ms
        tau_ms = beat_period_ms * DECAY_FRACTION
        return math.exp(-t_since_beat_ms / tau_ms)

    async def _run(self) -> None:
        while True:
            if not self._enabled:
                self._wake.clear()
                await self._wake.wait()
                continue

            try:
                env = self._envelope()
                target = int(self._bright_low + (self._bright_high - self._bright_low) * env)
                if abs(target - self._last_sent_brightness) >= BRIGHTNESS_DEADZONE:
                    try:
                        await self._bulb.set(self._rgb, target)
                        self._last_sent_brightness = target
                    except Exception as e:
                        log.warning("bulb set failed: %s", e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("beat loop error: %s", e)

            await asyncio.sleep(TICK_PERIOD)
