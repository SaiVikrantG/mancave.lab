import time
from dataclasses import dataclass, field


RGB = tuple[int, int, int]

AUDIO_FRESHNESS_SEC = 0.5


@dataclass
class ManualOverride:
    enabled: bool = False
    rgb: RGB = (255, 255, 255)
    brightness: int = 128


@dataclass
class State:
    """Shared mutable state across the Spotify poller, beat engine, audio
    listener, and web UI. Assumed to be touched only from the one asyncio loop.
    """
    # Live music state (written by main poll loop)
    is_playing: bool = False
    track_name: str = ""
    track_artist: str = ""
    track_id: str = ""
    energy: float = 0.0
    valence: float = 0.0
    tempo: float = 0.0
    # What the bulb is actually being driven to right now
    current_rgb: RGB = (0, 0, 0)
    current_brightness: int = 0
    # Live audio envelope (written by audio listener; 0 when no feed)
    audio_envelope: float = 0.0
    audio_last_seen: float = 0.0
    # Tuning knobs (editable from the dashboard)
    corner_sad: RGB = (0, 60, 255)
    corner_calm: RGB = (255, 100, 180)
    corner_angry: RGB = (255, 20, 0)
    corner_happy: RGB = (255, 200, 0)
    pulse_scale: float = 1.0
    decay_fraction: float = 0.30
    bright_floor: int = 20
    # Manual override — when enabled, mapping/pulse are bypassed
    manual: ManualOverride = field(default_factory=ManualOverride)

    def audio_fresh(self) -> bool:
        return (time.monotonic() - self.audio_last_seen) < AUDIO_FRESHNESS_SEC

    def snapshot(self) -> dict:
        return {
            "is_playing": self.is_playing,
            "track_name": self.track_name,
            "track_artist": self.track_artist,
            "energy": self.energy,
            "valence": self.valence,
            "tempo": self.tempo,
            "current_rgb": list(self.current_rgb),
            "current_brightness": self.current_brightness,
            "corners": {
                "sad": list(self.corner_sad),
                "calm": list(self.corner_calm),
                "angry": list(self.corner_angry),
                "happy": list(self.corner_happy),
            },
            "pulse_scale": self.pulse_scale,
            "decay_fraction": self.decay_fraction,
            "bright_floor": self.bright_floor,
            "manual": {
                "enabled": self.manual.enabled,
                "rgb": list(self.manual.rgb),
                "brightness": self.manual.brightness,
            },
            "audio": {
                "envelope": self.audio_envelope,
                "fresh": self.audio_fresh(),
            },
        }
