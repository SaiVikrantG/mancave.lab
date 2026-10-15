import tomllib
from pathlib import Path
from pydantic import BaseModel


class BulbConfig(BaseModel):
    ip: str


class SpotifyConfig(BaseModel):
    client_id: str
    client_secret: str
    refresh_token: str
    poll_interval_seconds: int = 5


class ReccoBeatsConfig(BaseModel):
    base_url: str = "https://api.reccobeats.com/v1"


class Config(BaseModel):
    bulb: BulbConfig
    spotify: SpotifyConfig
    reccobeats: ReccoBeatsConfig


def load(path: Path | str = "/etc/wizmood/config.toml") -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return Config.model_validate(raw)
