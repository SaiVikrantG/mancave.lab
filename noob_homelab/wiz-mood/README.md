# wiz-mood

Spotify-reactive mood lighting for a Philips WiZ bulb, running as an LXC service
on the homelab. Pivoted from the ESP32 attempt kept in `../esp32-archive/`.

**Status:** scaffold only. Bulb driver + config loader work; Spotify/ReccoBeats
polling and the mapping engine come next.

## Shape

- `src/wizmood/bulb.py` — thin wrapper around `pywizlight`.
- `src/wizmood/config.py` — loads `/etc/wizmood/config.toml` into a validated
  pydantic model.
- `src/wizmood/main.py` — entry point. Currently just drives the bulb once as
  proof of life.
- `config.example.toml` — shape of the deployed config. Real one lives at
  `/etc/wizmood/config.toml` on the LXC, mode 600, outside the repo.
- `scripts/`, `deploy/` — Spotify OAuth bootstrap and systemd unit, added in
  later phases.

## Deploy

Clone the parent repo on the LXC, create a venv at `/opt/wizmood/venv`, install
this package, and point the config file at it. Full runbook in `deploy/`.
