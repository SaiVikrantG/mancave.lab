from pywizlight import wizlight, PilotBuilder


class Bulb:
    def __init__(self, ip: str):
        self._light = wizlight(ip)

    async def set(self, rgb: tuple[int, int, int], brightness: int) -> None:
        await self._light.turn_on(PilotBuilder(rgb=rgb, brightness=brightness))

    async def off(self) -> None:
        await self._light.turn_off()
