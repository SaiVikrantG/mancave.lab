# Runbook 05: wiz-mood — Spotify-reactive WiZ bulb LXC

**When to use this:** building the `wizmood` LXC (vmid 102) from scratch to run the Spotify-reactive mood-lighting service against a Philips WiZ bulb on the home subnet. The service code lives at `noob_homelab/wiz-mood/` in this repo (pivoted from an earlier ESP32 attempt kept in `noob_homelab/esp32-archive/`).

**Prereqs:**
- Proxmox host up with the TP-Link cutover done (runbooks 01–04)
- A WiZ bulb reachable on the home subnet (`192.168.31.0/24`) with a known IP
- WiZ app → that bulb → Settings → Allow Local → **Allow all controls** enabled (newer firmwares default to "Only verified controls" which rejects unsigned local writes)
- Spotify developer app created at https://developer.spotify.com/dashboard with redirect URI `http://127.0.0.1:8765/callback` and Web API scope; **client_id** and **client_secret** copied
- A Mac on the lab subnet (for the audio tap and the one-time OAuth bootstrap)

**Expected time:** 45–60 min, assuming BlackHole and the Spotify app are already set up.

## Steps

### 1. Create the LXC

On the host Shell:

```bash
pveam list local        # confirm the Debian 13 template filename
pct create 102 local:vztmpl/<debian-13-standard_...>.tar.zst \
  --hostname wizmood \
  --cores 1 \
  --memory 512 \
  --swap 512 \
  --rootfs local-lvm:4 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp,firewall=1 \
  --unprivileged 1 \
  --features nesting=0 \
  --onboot 1 \
  --password
```

Notes:
- `512 MB` is comfortable; the service plus dashboard sits well under 100 MB resident.
- `nesting=0` — nothing inside the container runs sub-containers. (Proxmox prints a warning about systemd 257 and nesting; ignore unless systemd misbehaves inside.)
- DHCP on `vmbr0` — a TP-Link reservation can be added later; the lease is sticky in practice.
- `--password` prompts interactively for the container root password.

Start and enter:

```bash
pct start 102
pct enter 102
```

### 2. Base install inside the LXC

```bash
apt update && apt install -y python3 python3-venv python3-pip git nftables
ip addr show eth0 | grep 'inet '     # record the lab-subnet IP
```

Record the IP — you'll point the Mac audio tap at it.

### 3. Clone the repo and install the package in a venv

```bash
mkdir -p /opt/wizmood
git clone https://github.com/SaiVikrantG/mancave.lab.git /opt/wizmood/src
python3 -m venv /opt/wizmood/venv
/opt/wizmood/venv/bin/pip install --upgrade pip
/opt/wizmood/venv/bin/pip install -e /opt/wizmood/src/noob_homelab/wiz-mood/
```

Editable install means later `git pull` updates take effect without re-running pip.

**On token prompts:** for repeat pulls, either `git config --global credential.helper store` (plaintext in `~/.git-credentials`, fine inside an unprivileged LXC) or set up a GitHub deploy key with read-only scope.

### 4. Bootstrap the Spotify refresh token (runs on the Mac, not the LXC)

On the Mac, in a regular terminal:

```bash
cd /path/to/mancave.lab/noob_homelab/wiz-mood
python3 scripts/spotify_bootstrap.py
```

Enter client_id and client_secret when prompted. A browser tab opens Spotify's consent page; approve. The script catches the redirect at `127.0.0.1:8765/callback`, swaps the auth code for a refresh token, and prints the three values to paste into the LXC config.

Keep these somewhere safe for the next step; do not commit them.

### 5. Create the config file on the LXC

```bash
mkdir -p /etc/wizmood
cat > /etc/wizmood/config.toml <<'EOF'
[bulb]
ip = "192.168.31.XXX"            # the WiZ bulb's IP

[spotify]
client_id = ""
client_secret = ""
refresh_token = ""
poll_interval_seconds = 2

[reccobeats]
base_url = "https://api.reccobeats.com/v1"
EOF
chmod 600 /etc/wizmood/config.toml
```

Paste the three Spotify values into their fields, save.

### 6. Apply the egress firewall

The nftables ruleset in the repo locks the LXC down to: outbound 443/TCP (Spotify + ReccoBeats), DHCP + DNS, UDP/38899 to the bulb's specific IP, and inbound 8080/TCP + 38900/UDP from the lab subnet (dashboard + audio tap). Everything else drops.

```bash
cp /opt/wizmood/src/noob_homelab/wiz-mood/deploy/wizmood.nft /etc/nftables.conf
nft -c -f /etc/nftables.conf       # dry-run syntax check (no output = ok)
systemctl enable --now nftables
nft list ruleset                   # confirm rules loaded
```

**Check:** inbound 8080 and 38900 rules appear scoped to `192.168.50.0/24`; outbound 443 and the specific bulb UDP rule exist.

### 7. Start the service (manual for now)

```bash
/opt/wizmood/venv/bin/python3 -m wizmood.main
```

Expected startup logs include `audio listener on UDP :38900` and the bulb pulses purple briefly as a visible proof-of-life. If an unused `pct enter` session needs to stay open, run it in detached tmux instead:

```bash
apt install -y tmux
tmux new -d -s wizmood '/opt/wizmood/venv/bin/python3 -m wizmood.main'
tmux attach -t wizmood        # Ctrl-B then D to detach
```

systemd unit + non-login service user: deferred until the service stabilizes (see Gotchas).

### 8. Mac-side one-time setup for the audio tap

Done once, outside the LXC.

Install BlackHole and the Python audio deps:

```bash
brew install blackhole-2ch
pip3 install --user sounddevice numpy
```

Approve the BlackHole kernel-extension prompt in **System Settings → Privacy & Security** if it appears, then `sudo killall coreaudiod` so the driver registers without a reboot.

In **Audio MIDI Setup** (⌘-space → "audio midi"), create **two** Multi-Output Devices:
- **wizmood speakers** — real speakers + BlackHole 2ch. Real speakers as master. All members at 44100 Hz / 2 ch. Drift Correction on for BlackHole.
- **wizmood headphones** — BT headphones + BlackHole 2ch. Headphones as master. All members at 44100 Hz / 2 ch. Drift Correction on for BlackHole.

(BT headphones expose a 16 kHz HFP mono format next to the 44.1 kHz A2DP stereo format; pick the 44.1 kHz one — HFP is the voice-call profile and will sound awful.)

### 9. Run the audio tap

**System Settings → Sound → Output → pick whichever Multi-Output matches your current hardware.**

Then in a Mac terminal that stays open:

```bash
cd /path/to/mancave.lab/noob_homelab/wiz-mood
python3 scripts/audio_tap.py --target 192.168.50.XXX --rate 44100
```

(The IP is the LXC's lab-subnet address from step 2.)

macOS will ask once for microphone permission for the terminal app — approve it. Pumping music should produce `env=0.xx` lines every two seconds.

### 10. Verify end to end

Browser from the Mac: **http://192.168.50.XXX:8080**

Expected on the dashboard:
- Currently playing track + ReccoBeats energy/valence/tempo values.
- `pulse src` row showing **live tap (Mac)** in green while audio_tap.py runs; drops to **synthetic (BPM metronome)** within 500 ms of killing the tap.
- Envelope bar visibly wiggles with the music.
- Four color pickers for the sad/calm/angry/happy palette corners work live.
- Pulse / decay / floor sliders tune in real time.
- Manual override takes over immediately when toggled.

**A/B test for whether the audio tap is actually driving things:** play a loud passage, hit pause. Within 1–2 seconds the bulb should turn fully off (not freeze at mid-pulse brightness). Resume: it should come back to music-driven state.

### 11. Swap hardware mid-session

When you plug/unplug BT headphones mid-session:

- **System Settings → Sound → Output → switch to the matching Multi-Output preset.** Two clicks. BlackHole is in both so the LXC never notices.

If BT disconnects abruptly and audio stalls, the tap keeps sending `env=0`; the LXC still reports **live tap** on the dashboard but the bulb sits at low brightness. Swap presets to recover, or kill the tap to let the service fall back to synthetic mode until you're ready.

## Gotchas

- **WiZ "Only verified controls" firmware** — on recent WiZ Pro firmware (1.34+), unsigned local setPilot writes get rejected with `-32602 Invalid params`. Reads still work, which is a confusing partial-success signal. Fix: WiZ app → bulb → Settings → Security → Allow Local → **Allow all controls**. Must be flipped before anything speaks the local UDP protocol.
- **ReccoBeats coverage gaps** — not every track has features. The service logs `no features; leaving bulb unchanged` and the bulb keeps its last color. Pulse (brightness) still works because the audio tap is independent of the color path.
- **The service is still fake-metronome for the color** — color is a per-track average from ReccoBeats, not within-song. The audio tap only drives brightness/pulse. Expect color to stay constant through a song even if intensity shifts within it.
- **systemd + non-root service user: deferred.** Running the service as container-root under tmux is fine while the mapping is still being tuned. Switch to systemd + a dedicated `wizmood` user once there's no code change for a day or two — see the project's own README for the handoff.
- **ReccoBeats fetch is cached in memory only.** Service restart drops the cache; first play of a track after restart is slow (two HTTP round trips) before the color shows up. On-disk cache is a straightforward follow-up when it starts to annoy.
- **Mic permission is per-terminal-app.** iTerm, Terminal.app, VS Code integrated terminal each prompt once. Microphone access here is actually to BlackHole, not a real mic.
- **Jio DHCP and the bulb IP.** The bulb's IP on `192.168.31.0/24` is a DHCP lease. If it changes, `/etc/wizmood/config.toml` needs updating. A reservation on the AirFiber router — if its admin UI exposes DHCP reservations — avoids this.
- **Cross-subnet UDP relies on NAT keep-alive.** The TP-Link NAT entry for the bulb unicast expires if idle. The service sends setPilot often enough during playback to keep it warm; if the first command after a long idle times out, pywizlight retries. Harmless but may show as a one-line warning.
- **Dashboard tweaks don't persist.** Palette corners, floor, decay, pulse scale all reset on service restart. Config write-back from the dashboard is a planned follow-up.
