import asyncio
import logging
import time

from wizmood.bulb import Bulb

log = logging.getLogger("wizmood.beat")

MIN_BPM = 60.0
MAX_BPM = 180.0


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
        brightness: int,
        bpm: float,
        progress_ms: int,
    ) -> None:
        self._rgb = rgb
        self._bright_high = brightness
        self._bright_low = max(10, int(brightness * 0.55))
        self._bpm = _clamp_bpm(bpm) if bpm > 0 else 0.0
        self._anchor_song_ms = float(progress_ms)
        self._anchor_wall = time.monotonic()
        self._enabled = self._bpm > 0
        self._wake.set()

    def disable(self) -> None:
        self._enabled = False
        self._wake.set()

    def _current_song_ms(self) -> float:
        return self._anchor_song_ms + (time.monotonic() - self._anchor_wall) * 1000.0

    async def _sleep_until_next_half_beat(self) -> bool:
        """Returns True if we're on a down-beat, False if on an up-beat."""
        half_period_ms = 30000.0 / self._bpm
        song_ms = self._current_song_ms()
        halves_elapsed = song_ms / half_period_ms
        remainder = halves_elapsed - int(halves_elapsed)
        wait_ms = (1.0 - remainder) * half_period_ms
        await asyncio.sleep(wait_ms / 1000.0)
        # The half-beat we just landed on:
        return (int(halves_elapsed) + 1) % 2 == 0

    async def _run(self) -> None:
        while True:
            if not self._enabled:
                self._wake.clear()
                await self._wake.wait()
                continue

            try:
                on_beat = await self._sleep_until_next_half_beat()
                brightness = self._bright_high if on_beat else self._bright_low
                try:
                    await self._bulb.set(self._rgb, brightness)
                except Exception as e:
                    log.warning("bulb set failed: %s", e)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("beat loop error: %s", e)
                await asyncio.sleep(0.5)
