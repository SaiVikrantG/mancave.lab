# ESP32 WiZ Bulb + Spotify Mood Lighting — Project Brief

## What we're building

A self-contained ESP32-WROOM-32 device that controls a Philips WiZ smart bulb (WiFi, E27) and makes it react to whatever's currently playing on Spotify — brightness, color, and a beat-driven pulse based on the track's actual audio characteristics (energy, valence, tempo), not just a simple on/off.

Beyond the core lighting behavior, the project has two other explicit goals:

- **Extensibility**: the firmware's web server is architected so new features can be added later (one new file + one registration line) without reworking existing code.
- **A tuning dashboard**: a web UI served from the device itself, letting the user manually adjust how audio characteristics map to bulb behavior (brightness curve, color mapping, beat-pulse intensity), with manual override always winning over the automatic mapping.

## Key design decisions and why

- **No local audio capture.** Originally considered reacting to audio picked up live (mic/loopback), but ruled out once the plan shifted to hosting everything on the ESP32 — the chip can't do real-time DSP and also run WiFi/web server/UDP comfortably.
- **Spotify's own audio-features API is dead.** Spotify permanently deprecated `audio-features`/`audio-analysis`/`recommendations` for new developer apps in November 2024. Instead, the plan uses Spotify's still-open `currently-playing` endpoint to identify the track, then looks up its characteristics via **ReccoBeats**, a free third-party API that mirrors Spotify's old audio-features schema by track ID.
- **No real beat-grid exists**, so "beat sync" is approximated: the firmware computes BPM from ReccoBeats, then runs a locally-simulated metronome phase-aligned to Spotify's reported playback position, re-synced on every poll.
- **Board/framework**: ESP32-WROOM-32 (classic), C++ via the **Arduino framework**, built with **PlatformIO** in VS Code. MicroPython was considered and rejected — the classic ESP32's ~320KB usable RAM is already tight once you factor in TLS sessions (HTTPS to Spotify + ReccoBeats) running alongside an async web server, WebSocket, and UDP; MicroPython's interpreter overhead and thinner async-networking library ecosystem made it a worse fit here.
- **WiFi credentials** are never hardcoded — a WiFiManager-driven captive portal collects them on first boot and persists them to flash.
- **Spotify OAuth** is bootstrapped once via a small Python script run on the Mac (not on the device) to obtain a refresh token, which is then pasted into the ESP32's config. The device only ever uses the refresh-token grant from then on.
- **Dashboard assets** (HTML/CSS/JS) live on the ESP32's LittleFS filesystem as static files, not inlined in C++ — keeps firmware code and UI code separate as the project grows.

## Architecture (planned)

Every feature area is a module implementing a common `IModule` interface (`begin()`, `registerRoutes()`, `loop()`), registered into a shared `AsyncWebServer`/`AsyncWebSocket` instance at boot. Planned modules: WiFi provisioning, bulb control (WiZ UDP protocol), Spotify polling, ReccoBeats lookup, the mapping/pulse engine, and the dashboard. Config is split between NVS (WiFi creds, bulb IP) and LittleFS JSON (Spotify secrets, dashboard tuning params), all routed through a single `ConfigStore` module.

Full detail lives in the approved implementation plan: `/Users/vikrant/.claude/plans/alright-create-a-plan-binary-pancake.md`.

## Build order

1. **WiFi provisioning + bulb on/off smoke test** ← *we are here*
2. Modular web server skeleton + LittleFS dashboard shell
3. Spotify polling
4. ReccoBeats lookup + mapping/pulse engine
5. Dashboard tuning controls + WebSocket live state

## What's implemented so far (Phase 1)

- Git repo initialized; `.gitignore` excludes build artifacts and any future secrets files (`include/secrets.h`, `data/secrets.json`).
- `platformio.ini` — targets `esp32dev`/Arduino framework, LittleFS filesystem, pulls in `WiFiManager` and `ArduinoJson`. Upload speed was dropped to 115200 (from the default 921600) to work around a flaky USB connection.
- `include/config.h` — WiZ UDP port (38899), discovery timeout, captive-portal AP name (`ESP32-WizLight-Setup`).
- `src/main.cpp` — one-shot smoke test:
  - Boots WiFiManager; puts up the captive portal if no WiFi credentials are saved yet, otherwise connects directly.
  - Broadcasts a WiZ `getPilot` discovery packet over UDP and logs any bulb replies to Serial.
  - Sends `setState(true)` to the first discovered bulb, waits 2 seconds, then sends `setState(false)`.
- Not yet implemented: the module system, web server, dashboard, Spotify integration, ReccoBeats integration, and the mapping engine — all of that starts in Phase 2 onward.

## Current status / in-progress troubleshooting

Hardware setup is still being debugged before Phase 1 can be verified end-to-end:

- ESP32 board confirmed connected and recognized by macOS as `/dev/cu.usbmodemSN234567892` (verified via plug/unplug correlation).
- Firmware builds successfully (13.9% RAM, 66.3% flash used).
- Upload currently fails with `esptool`'s "Failed to connect to ESP32: No serial data received" — working through Espressif's official troubleshooting steps in order: lowered upload baud rate (115200, done), manual BOOT-button boot-mode entry (tried), cable swap (tried, no change). Current leading suspect: **a USB hub sits between the MacBook and the ESP32** (no direct USB-C-to-USB-B cable on hand) — Espressif's docs explicitly list eliminating USB hubs as a fix for this exact error. Next step is testing with a direct USB-C-to-USB-A connection (bypassing the hub) to confirm.
