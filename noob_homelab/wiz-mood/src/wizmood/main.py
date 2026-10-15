import asyncio
import logging

from wizmood.bulb import Bulb
from wizmood.config import load


async def run() -> None:
    cfg = load()
    bulb = Bulb(cfg.bulb.ip)
    await bulb.set((140, 60, 180), 40)
    await asyncio.sleep(2)
    await bulb.off()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
