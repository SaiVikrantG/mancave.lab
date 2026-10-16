from dataclasses import dataclass

from wizmood.reccobeats import AudioFeatures
from wizmood.state import State


@dataclass
class BulbState:
    rgb: tuple[int, int, int]
    bright_high: int
    bright_low: int


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _bilinear(state: State, v: float, e: float) -> tuple[int, int, int]:
    w_sad   = (1 - v) * (1 - e)
    w_calm  = v       * (1 - e)
    w_angry = (1 - v) * e
    w_happy = v       * e
    pairs = (
        (state.corner_sad,   w_sad),
        (state.corner_calm,  w_calm),
        (state.corner_angry, w_angry),
        (state.corner_happy, w_happy),
    )
    r = sum(c[0] * w for c, w in pairs)
    g = sum(c[1] * w for c, w in pairs)
    b = sum(c[2] * w for c, w in pairs)
    return int(r), int(g), int(b)


def map_features(state: State, f: AudioFeatures) -> BulbState:
    energy = _clamp(f.energy)
    valence = _clamp(f.valence)

    rgb = _bilinear(state, valence, energy)

    # bright_target maps energy linearly from the floor up to 255.
    floor = max(1, min(254, state.bright_floor))
    bright_target = int(floor + (255 - floor) * energy)

    # pulse_scale lets the dashboard turn the pulse up/down globally.
    pulse_amplitude = int((4 + 106 * (energy ** 2)) * state.pulse_scale)

    bright_high = min(255, bright_target + pulse_amplitude // 2)
    bright_low  = max(1, bright_target - pulse_amplitude // 2)

    return BulbState(rgb=rgb, bright_high=bright_high, bright_low=bright_low)
