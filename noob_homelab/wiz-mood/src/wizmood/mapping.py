from dataclasses import dataclass

from wizmood.reccobeats import AudioFeatures


@dataclass
class BulbState:
    rgb: tuple[int, int, int]
    bright_high: int
    bright_low: int


# Four corners of the (valence, energy) plane. Edit these to retune the vibe;
# everything in between is a bilinear interpolation of the four.
CORNER_SAD   = (0,   60,  255)   # low valence, low energy  — deep blue
CORNER_CALM  = (255, 100, 180)   # high valence, low energy — soft pink
CORNER_ANGRY = (255, 20,  0)     # low valence, high energy — hard red
CORNER_HAPPY = (255, 200, 0)     # high valence, high energy — warm yellow


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _bilinear(v: float, e: float) -> tuple[int, int, int]:
    w_sad   = (1 - v) * (1 - e)
    w_calm  = v       * (1 - e)
    w_angry = (1 - v) * e
    w_happy = v       * e
    corners = (
        (CORNER_SAD,   w_sad),
        (CORNER_CALM,  w_calm),
        (CORNER_ANGRY, w_angry),
        (CORNER_HAPPY, w_happy),
    )
    r = sum(c[0] * w for c, w in corners)
    g = sum(c[1] * w for c, w in corners)
    b = sum(c[2] * w for c, w in corners)
    return int(r), int(g), int(b)


def map_features(f: AudioFeatures) -> BulbState:
    energy = _clamp(f.energy)
    valence = _clamp(f.valence)

    rgb = _bilinear(valence, energy)

    # Target brightness scales with energy: calm sits dim, angry runs hot.
    bright_target = int(80 + 175 * energy)

    # Pulse amplitude also scales with energy, but much more aggressively so
    # that below ~0.3 energy the pulse is essentially invisible (steady glow).
    # amplitude ranges from ~4 (energy=0) up to ~110 (energy=1).
    pulse_amplitude = int(4 + 106 * (energy ** 2))

    bright_high = min(255, bright_target + pulse_amplitude // 2)
    bright_low  = max(10, bright_target - pulse_amplitude // 2)

    return BulbState(rgb=rgb, bright_high=bright_high, bright_low=bright_low)
