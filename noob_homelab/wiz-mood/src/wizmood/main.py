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
    bulb: Bulb,
    spotify: SpotifyClient,
    reccobeats: ReccoBeatsClient,
    beat: BeatEngine,
) -> None:
    last_id: str | None = None
    features_by_id: dict[str, AudioFeatures | None] = {}
    fetch_tasks: dict[str, asyncio.Task] = {}

    def start_fetch(track_id: str) -> None:
        if track_id in features_by_id or track_id in fetch_tasks:
            return
        async def go():
            try:
                feat = await reccobeats.features_for_spotify_track(track_id)
                features_by_id[track_id] = feat
                if feat is None:
                    log.info("no features for %s", track_id)
            finally:
                fetch_tasks.pop(track_id, None)
        fetch_tasks[track_id] = asyncio.create_task(go())

    while True:
        np = await spotify.currently_playing()

        if np is None or not np.is_playing:
            state.is_playing = False
            if last_id is not None:
                log.info("paused / nothing playing; bulb off")
                beat.disable()
                try:
                    await bulb.off()
                except Exception as e:
                    log.warning("bulb off failed: %s", e)
                last_id = None
        else:
            state.is_playing = True
            state.track_id = np.track_id
            state.track_name = np.name
            state.track_artist = np.artist

            if np.track_id != last_id:
                log.info("now: %s - %s", np.artist, np.name)
                last_id = np.track_id
                start_fetch(np.track_id)

            feat = features_by_id.get(np.track_id)
            if feat is not None:
                state.energy = feat.energy
                state.valence = feat.valence
                state.tempo = feat.tempo
                mapped = map_features(state, feat)
                beat.update(
                    rgb=mapped.rgb,
                    bright_high=mapped.bright_high,
                    bright_low=mapped.bright_low,
                    bpm=feat.tempo,
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

    poll_task = asyncio.create_task(_poll_loop(cfg, state, bulb, spotify, reccobeats, beat))

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
