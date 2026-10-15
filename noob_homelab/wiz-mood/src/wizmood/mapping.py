import colorsys
from dataclasses import dataclass

from wizmood.reccobeats import AudioFeatures


@dataclass
class BulbState:
    rgb: tuple[int, int, int]
    bright_high: int
    bright_low: int


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def map_features(f: AudioFeatures) -> BulbState:
    energy = _clamp(f.energy)
    valence = _clamp(f.valence)

    # Hue: valence 0 → blue (2/3), valence 1 → red (0).
    hue = (1.0 - valence) * (2.0 / 3.0)

    # Saturation: energy drives how saturated the color is.
    # Calm songs → pastel (sat ~0.35); angry/intense → fully saturated.
    saturation = 0.35 + 0.65 * energy

    r, g, b = colorsys.hsv_to_rgb(hue, saturation, 1.0)
    rgb = (int(r * 255), int(g * 255), int(b * 255))

    # Brightness floor + headroom both scale with energy.
    # Calm: floor 50, high 100 (small pulse)
    # Angry: floor 120, high 255 (big pulse)
    bright_high = int(100 + 155 * energy)
    bright_low = int(50 + 70 * energy)
    # Clamp high above low in case of rounding at extremes.
    bright_low = min(bright_low, bright_high - 10)

    return BulbState(rgb=rgb, bright_high=bright_high, bright_low=bright_low)
