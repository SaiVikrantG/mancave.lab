# ESP32 archive

Original Phase 1 attempt at the WiZ + Spotify mood-lighting project, targeting an
ESP32-WROOM-32. Abandoned in favor of running the same service as an LXC on the
homelab — the ESP32 was too tight on RAM once TLS + async web + UDP all had to
coexist, and the final blocker was a flashing/USB-hub issue that wasn't worth
chasing further.

Kept here for reference (platformio.ini, the WiZ UDP discovery/setState code in
`src/main.cpp`, and the original design notes in `PROJECT_BRIEF.md`). The LXC
rewrite lives at the repo root.
