import colorsys
from dataclasses import dataclass

from wizmood.reccobeats import AudioFeatures


@dataclass
class BulbState:
    rgb: tuple[int, int, int]
    brightness: int


def map_features(f: AudioFeatures) -> BulbState:
    # valence: 0 → blue, 1 → red. HSV hue goes 0 (red) → 2/3 (blue), so invert.
    hue = (1.0 - max(0.0, min(1.0, f.valence))) * (2.0 / 3.0)
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    rgb = (int(r * 255), int(g * 255), int(b * 255))

    # energy: 0 → 30 (dim but visible), 1 → 255. Keep a floor so the room is lit.
    brightness = int(30 + max(0.0, min(1.0, f.energy)) * (255 - 30))

    return BulbState(rgb=rgb, brightness=brightness)
