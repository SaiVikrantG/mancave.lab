import asyncio
import logging
import math
import struct
import time

from wizmood.state import State

log = logging.getLogger("wizmood.audio")

LISTEN_PORT = 38900


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, state: State) -> None:
        self._state = state

    def datagram_received(self, data: bytes, addr) -> None:
        # Strict shape: a single little-endian float32 in [0, 1].
        if len(data) != 4:
            return
        try:
            (value,) = struct.unpack("<f", data)
        except struct.error:
            return
        if not math.isfinite(value):
            return
        self._state.audio_envelope = max(0.0, min(1.0, float(value)))
        self._state.audio_last_seen = time.monotonic()


async def start_listener(state: State, port: int = LISTEN_PORT):
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Protocol(state),
        local_addr=("0.0.0.0", port),
    )
    log.info("audio listener on UDP :%d", port)
    return transport
