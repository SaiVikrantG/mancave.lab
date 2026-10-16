import asyncio
import logging

import uvicorn

from wizmood.audio import start_listener as start_audio_listener
from wizmood.beat import BeatEngine
from wizmood.bulb import Bulb
from wizmood.config import load
from wizmood.mapping import map_features
from wizmood.reccobeats import AudioFeatures, ReccoBeatsClient
from wizmood.spotify import SpotifyClient
from wizmood.state import State
from wizmood.web import build_app

log = logging.getLogger("wizmood")


async def _poll_loop(
    cfg,
    state: State,
    spotify: SpotifyClient,
    reccobeats: ReccoBeatsClient,
    beat: BeatEngine,
) -> None:
    last_id: str | None = None
    cached_features: AudioFeatures | None = None

    while True:
        np = await spotify.currently_playing()

        if np is None or not np.is_playing:
            state.is_playing = False
            if last_id is not None:
                log.info("paused / nothing playing")
                beat.disable()
                last_id = None
                cached_features = None
        else:
            state.is_playing = True
            state.track_id = np.track_id
            state.track_name = np.name
            state.track_artist = np.artist

            if np.track_id != last_id:
                log.info("now: %s - %s", np.artist, np.name)
                last_id = np.track_id
                cached_features = await reccobeats.features_for_spotify_track(np.track_id)
                if cached_features is None:
                    log.info("no features; leaving bulb unchanged")
                else:
                    state.energy = cached_features.energy
                    state.valence = cached_features.valence
                    state.tempo = cached_features.tempo

            if cached_features is not None:
                mapped = map_features(state, cached_features)
                beat.update(
                    rgb=mapped.rgb,
                    bright_high=mapped.bright_high,
                    bright_low=mapped.bright_low,
                    bpm=cached_features.tempo,
                    progress_ms=np.progress_ms,
                )

        await asyncio.sleep(cfg.spotify.poll_interval_seconds)


async def run() -> None:
    cfg = load()
    state = State()

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
    beat = BeatEngine(bulb, state)
    beat.start()

    audio_transport = await start_audio_listener(state)

    app = build_app(state)
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning")
    server = uvicorn.Server(uv_config)
    server_task = asyncio.create_task(server.serve())

    poll_task = asyncio.create_task(_poll_loop(cfg, state, spotify, reccobeats, beat))

    try:
        await asyncio.gather(poll_task, server_task)
    finally:
        audio_transport.close()
        await beat.stop()
        await spotify.close()
        await reccobeats.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
