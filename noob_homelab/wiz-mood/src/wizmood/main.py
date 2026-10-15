import asyncio
import logging

from wizmood.beat import BeatEngine
from wizmood.bulb import Bulb
from wizmood.config import load
from wizmood.mapping import map_features
from wizmood.reccobeats import AudioFeatures, ReccoBeatsClient
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
    beat = BeatEngine(bulb)
    beat.start()

    try:
        last_id: str | None = None
        cached_features: AudioFeatures | None = None

        while True:
            np = await spotify.currently_playing()

            if np is None or not np.is_playing:
                if last_id is not None:
                    log.info("paused / nothing playing; bulb off")
                    beat.disable()
                    await bulb.off()
                    last_id = None
                    cached_features = None
            else:
                if np.track_id != last_id:
                    log.info("now: %s - %s", np.artist, np.name)
                    last_id = np.track_id
                    cached_features = await reccobeats.features_for_spotify_track(np.track_id)
                    if cached_features is None:
                        log.info("no features; leaving bulb unchanged")

                if cached_features is not None:
                    state = map_features(cached_features)
                    beat.update(
                        rgb=state.rgb,
                        brightness=state.brightness,
                        bpm=cached_features.tempo,
                        progress_ms=np.progress_ms,
                    )

            await asyncio.sleep(cfg.spotify.poll_interval_seconds)
    finally:
        await beat.stop()
        await spotify.close()
        await reccobeats.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
