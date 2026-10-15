import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from wizmood.state import State

log = logging.getLogger("wizmood.web")

STATIC_DIR = Path(__file__).parent / "static"


def _clamp_int(x, lo, hi) -> int:
    return max(lo, min(hi, int(x)))


def _parse_rgb(value) -> tuple[int, int, int]:
    r, g, b = value
    return _clamp_int(r, 0, 255), _clamp_int(g, 0, 255), _clamp_int(b, 0, 255)


def build_app(state: State) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        try:
            # Push initial state
            await socket.send_text(json.dumps(state.snapshot()))

            async def pusher():
                import asyncio
                while True:
                    await asyncio.sleep(0.5)
                    await socket.send_text(json.dumps(state.snapshot()))

            import asyncio
            push_task = asyncio.create_task(pusher())

            try:
                while True:
                    msg = await socket.receive_text()
                    _handle(state, json.loads(msg))
            finally:
                push_task.cancel()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            log.warning("ws error: %s", e)

    return app


def _handle(state: State, msg: dict) -> None:
    t = msg.get("type")
    if t == "set_corner":
        name = msg.get("corner")
        rgb = _parse_rgb(msg.get("rgb", [0, 0, 0]))
        attr = f"corner_{name}"
        if hasattr(state, attr):
            setattr(state, attr, rgb)
    elif t == "set_pulse_scale":
        state.pulse_scale = max(0.0, min(3.0, float(msg.get("value", 1.0))))
    elif t == "set_decay_fraction":
        state.decay_fraction = max(0.05, min(0.9, float(msg.get("value", 0.3))))
    elif t == "set_manual":
        m = msg.get("manual", {})
        state.manual.enabled = bool(m.get("enabled", False))
        if "rgb" in m:
            state.manual.rgb = _parse_rgb(m["rgb"])
        if "brightness" in m:
            state.manual.brightness = _clamp_int(m["brightness"], 10, 255)
