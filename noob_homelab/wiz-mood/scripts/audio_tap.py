"""Mac-side audio tap. Reads system audio from a BlackHole loopback device,
computes an auto-gained RMS envelope at 20 Hz, and UDP-ships it to the wizmood
LXC. Run while music is playing; the LXC's beat engine will prefer this real
envelope over its synthetic fallback.

Setup (one-time, on the Mac):
  1. brew install blackhole-2ch
     (or install the .pkg from https://github.com/ExistentialAudio/BlackHole)
  2. Audio MIDI Setup → + → Create Multi-Output Device.
     Check your real speakers AND BlackHole 2ch. Mark your real speakers
     as the master device.
  3. System Settings → Sound → Output → pick the Multi-Output Device.
     You'll still hear music; BlackHole gets a parallel copy.

Run:
  pip install sounddevice numpy
  python3 scripts/audio_tap.py --target 192.168.50.104

The script auto-discovers BlackHole as the input device. If you have more than
one BlackHole variant installed, pass --device "BlackHole 2ch".
"""

import argparse
import socket
import struct
import sys
import time

import numpy as np
import sounddevice as sd

DEFAULT_PORT = 38900
TARGET_HZ = 20
PEAK_DECAY = 0.995     # per block; ~140 blocks (~7s) to halve
NOISE_FLOOR = 0.002    # ignore RMS below this (silence)


def find_input(hint: str) -> int:
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        name = d["name"]
        if hint.lower() in name.lower() and d["max_input_channels"] >= 1:
            return i
    print(f"error: no input device matching {hint!r} found. Available inputs:",
          file=sys.stderr)
    for i, d in enumerate(devices):
        if d["max_input_channels"] >= 1:
            print(f"  [{i}] {d['name']}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="wizmood audio tap for Mac")
    ap.add_argument("--target", required=True,
                    help="LXC IP, e.g. 192.168.50.104")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--device", default="BlackHole",
                    help='Input device name substring (default "BlackHole")')
    ap.add_argument("--rate", type=int, default=48000,
                    help="Audio sample rate (default 48000)")
    args = ap.parse_args()

    device_index = find_input(args.device)
    info = sd.query_devices(device_index)
    channels = min(2, info["max_input_channels"])
    block_size = args.rate // TARGET_HZ

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.target, args.port)

    peak = 0.05  # start with a modest ceiling so first block isn't crushed
    sent = 0
    last_print = time.monotonic()

    def callback(indata, frames, time_info, status):
        nonlocal peak, sent, last_print
        if status:
            print(f"stream status: {status}", file=sys.stderr)
        # RMS across all channels in this block
        rms = float(np.sqrt(np.mean(indata ** 2)))
        if rms < NOISE_FLOOR:
            value = 0.0
        else:
            peak = max(peak * PEAK_DECAY, rms)
            value = min(1.0, rms / (peak + 1e-9))
        try:
            sock.sendto(struct.pack("<f", value), target)
            sent += 1
        except OSError as e:
            print(f"send failed: {e}", file=sys.stderr)
        now = time.monotonic()
        if now - last_print > 2.0:
            print(f"env={value:.2f}  peak={peak:.3f}  sent={sent}  → {target[0]}:{target[1]}")
            last_print = now

    print(f"using device [{device_index}] {info['name']} @ {args.rate} Hz, {channels}ch")
    print(f"sending envelope to udp://{args.target}:{args.port} at {TARGET_HZ} Hz")
    print("Ctrl-C to stop.\n")

    try:
        with sd.InputStream(
            device=device_index,
            channels=channels,
            samplerate=args.rate,
            blocksize=block_size,
            callback=callback,
        ):
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
