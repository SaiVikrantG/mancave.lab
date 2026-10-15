import asyncio
import logging

from wizmood.bulb import Bulb
from wizmood.config import load
from wizmood.mapping import map_features
from wizmood.reccobeats import ReccoBeatsClient
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
    reccobeats = ReccoBeatsClient(cfg.reccobeats.base_url)

    try:
        last_id: str | None = None
        while True:
            np = await spotify.currently_playing()
            if np is None:
                if last_id is not None:
                    log.info("nothing playing; bulb off")
                    await bulb.off()
                    last_id = None
            elif np.track_id != last_id:
                log.info("now: %s - %s", np.artist, np.name)
                last_id = np.track_id
                features = await reccobeats.features_for_spotify_track(np.track_id)
                if features is None:
                    log.info("no features; leaving bulb unchanged")
                else:
                    state = map_features(features)
                    log.info(
                        "features e=%.2f v=%.2f t=%.0f → rgb=%s b=%d",
                        features.energy, features.valence, features.tempo,
                        state.rgb, state.brightness,
                    )
                    await bulb.set(state.rgb, state.brightness)
            await asyncio.sleep(cfg.spotify.poll_interval_seconds)
    finally:
        await spotify.close()
        await reccobeats.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
