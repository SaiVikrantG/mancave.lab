import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger("wizmood.reccobeats")


@dataclass
class AudioFeatures:
    energy: float
    valence: float
    tempo: float
    danceability: float


class ReccoBeatsClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=10.0)
        # Simple unbounded in-memory cache. Spotify IDs are 22 chars so this
        # stays small even over months of use; worth capping only if someone
        # listens to tens of thousands of unique tracks in one session.
        self._cache: dict[str, AudioFeatures | None] = {}

    async def close(self) -> None:
        await self._http.aclose()

    async def features_for_spotify_track(self, spotify_id: str) -> AudioFeatures | None:
        if spotify_id in self._cache:
            return self._cache[spotify_id]
        result = await self._fetch(spotify_id)
        self._cache[spotify_id] = result
        return result

    async def _fetch(self, spotify_id: str) -> AudioFeatures | None:
        try:
            resolve = await self._http.get(
                f"{self._base_url}/track",
                params={"ids": spotify_id},
            )
            resolve.raise_for_status()
            content = resolve.json().get("content") or []
            if not content:
                log.info("reccobeats: no match for spotify id %s", spotify_id)
                return None
            uuid = content[0].get("id")
            if not uuid:
                log.info("reccobeats: resolve returned no id for %s", spotify_id)
                return None

            feat = await self._http.get(
                f"{self._base_url}/track/{uuid}/audio-features",
            )
            feat.raise_for_status()
            payload = feat.json()
            return AudioFeatures(
                energy=float(payload["energy"]),
                valence=float(payload["valence"]),
                tempo=float(payload["tempo"]),
                danceability=float(payload["danceability"]),
            )
        except httpx.HTTPError as e:
            log.warning("reccobeats: request failed: %s", e)
            return None
        except (KeyError, ValueError) as e:
            log.warning("reccobeats: unexpected response shape: %s", e)
            return None
