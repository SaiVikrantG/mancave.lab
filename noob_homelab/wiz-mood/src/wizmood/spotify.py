import base64
import time
from dataclasses import dataclass

import httpx

TOKEN_URL = "https://accounts.spotify.com/api/token"
CURRENTLY_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"


@dataclass
class NowPlaying:
    track_id: str
    name: str
    artist: str
    progress_ms: int
    duration_ms: int
    is_playing: bool


class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._access_expires_at: float = 0.0
        self._http = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def _ensure_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._access_expires_at - 60:
            return self._access_token
        auth = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = await self._http.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            headers={"Authorization": f"Basic {auth}"},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._access_token = payload["access_token"]
        self._access_expires_at = time.monotonic() + payload.get("expires_in", 3600)
        return self._access_token

    async def currently_playing(self) -> NowPlaying | None:
        token = await self._ensure_access_token()
        resp = await self._http.get(
            CURRENTLY_PLAYING_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 204 or not resp.content:
            return None
        resp.raise_for_status()
        payload = resp.json()
        item = payload.get("item")
        if not item or item.get("type") != "track":
            return None
        return NowPlaying(
            track_id=item["id"],
            name=item["name"],
            artist=", ".join(a["name"] for a in item.get("artists", [])),
            progress_ms=payload.get("progress_ms", 0),
            duration_ms=item.get("duration_ms", 0),
            is_playing=payload.get("is_playing", False),
        )
