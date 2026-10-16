import asyncio
import logging
import math
import time

from wizmood.bulb import Bulb
from wizmood.state import State

log = logging.getLogger("wizmood.beat")

MIN_BPM = 60.0
MAX_BPM = 180.0

TICK_HZ = 20
TICK_PERIOD = 1.0 / TICK_HZ

BRIGHTNESS_DEADZONE = 3


def _clamp_bpm(bpm: float) -> float:
    while bpm > MAX_BPM:
        bpm /= 2
    while bpm < MIN_BPM:
        bpm *= 2
    return bpm


class BeatEngine:
    def __init__(self, bulb: Bulb, state: State) -> None:
        self._bulb = bulb
        self._state = state
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
        self._last_sent_rgb: tuple[int, int, int] = (-1, -1, -1)

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
        self._rgb = rgb
        self._bright_high = bright_high
        self._bright_low = max(10, bright_low)
        self._bpm = _clamp_bpm(bpm) if bpm > 0 else 0.0
        self._anchor_song_ms = float(progress_ms)
        self._anchor_wall = time.monotonic()
        self._enabled = self._bpm > 0
        self._wake.set()

    def disable(self) -> None:
        self._enabled = False
        self._last_sent_brightness = -1
        self._wake.set()

    def _current_song_ms(self) -> float:
        return self._anchor_song_ms + (time.monotonic() - self._anchor_wall) * 1000.0

    def _envelope(self) -> float:
        beat_period_ms = 60000.0 / self._bpm
        song_ms = self._current_song_ms()
        t_since_beat_ms = song_ms % beat_period_ms
        tau_ms = max(1.0, beat_period_ms * self._state.decay_fraction)
        return math.exp(-t_since_beat_ms / tau_ms)

    async def _apply(self, rgb: tuple[int, int, int], brightness: int) -> None:
        if (
            rgb == self._last_sent_rgb
            and abs(brightness - self._last_sent_brightness) < BRIGHTNESS_DEADZONE
        ):
            return
        try:
            await self._bulb.set(rgb, brightness)
            self._last_sent_rgb = rgb
            self._last_sent_brightness = brightness
            self._state.current_rgb = rgb
            self._state.current_brightness = brightness
        except Exception as e:
            log.warning("bulb set failed: %s", e)

    async def _run(self) -> None:
        while True:
            try:
                # Manual override wins over everything.
                if self._state.manual.enabled:
                    await self._apply(self._state.manual.rgb, self._state.manual.brightness)
                    await asyncio.sleep(TICK_PERIOD)
                    continue

                if not self._enabled:
                    self._wake.clear()
                    # Still wake periodically so manual overrides turn on quickly.
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=0.2)
                    except asyncio.TimeoutError:
                        pass
                    continue

                if self._state.audio_fresh():
                    env = self._state.audio_envelope
                else:
                    env = self._envelope()
                target = int(self._bright_low + (self._bright_high - self._bright_low) * env)
                await self._apply(self._rgb, target)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("beat loop error: %s", e)

            await asyncio.sleep(TICK_PERIOD)
