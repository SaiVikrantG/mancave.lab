import asyncio
import logging

from wizmood.bulb import Bulb
from wizmood.config import load
from wizmood.spotify import SpotifyClient

log = logging.getLogger("wizmood")


async def run() -> None:
    cfg = load()

    bulb = Bulb(cfg.bulb.ip)
    await bulb.set((140, 60, 180), 40)
    await asyncio.sleep(1)
    await bulb.off()

    spotify = SpotifyClient(
        cfg.spotify.client_id,
        cfg.spotify.client_secret,
        cfg.spotify.refresh_token,
    )
    try:
        last_id: str | None = None
        while True:
            np = await spotify.currently_playing()
            if np is None:
                if last_id is not None:
                    log.info("nothing playing")
                    last_id = None
            elif np.track_id != last_id:
                log.info("now: %s - %s (playing=%s)", np.artist, np.name, np.is_playing)
                last_id = np.track_id
            await asyncio.sleep(cfg.spotify.poll_interval_seconds)
    finally:
        await spotify.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
