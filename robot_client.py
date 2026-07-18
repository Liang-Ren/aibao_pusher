import asyncio
import logging
import time

import websockets

import config
import protocol

log = logging.getLogger("robot_client")


def _to_bytes(message) -> bytes:
    """The relay sends every server->client message as a hex-encoded ASCII
    text frame (not a binary frame) — see 4wd.php's hexToBytes(). Outgoing
    client->server messages are plain binary, so this only applies on recv."""
    if isinstance(message, str):
        return bytes.fromhex(message)
    return bytes(message)

# action name -> encode_control_body() kwargs (see protocol.py for axis meaning)
ACTION_BODY_KWARGS = {
    "wheel_forward":    {"joystick_y": 1.0},
    "wheel_backward":   {"joystick_y": -1.0},
    "wheel_left":       {"joystick_x": -1.0},
    "wheel_right":      {"joystick_x": 1.0},
}

ARM_ACTIONS = set()  # arm was physically removed; kept as a no-op set for act()'s branch below


class RobotClient:
    """WebSocket client for the IFUUU-4WD cloud relay. See protocol.py for
    the wire format. DRY_RUN logs intended actions/frame-waits instead of
    opening a real connection, for developing the vision loop offline."""

    def __init__(self):
        self.ws = None
        self.own_id: bytes | None = None
        self.device_id = bytes.fromhex(config.ROBOT_DEVICE_ID) if config.ROBOT_DEVICE_ID else b""
        self._latest_frame: bytes | None = None
        self._frame_chunks: dict[int, bytes] = {}
        self._recv_task = None
        self._video_request_task = None

    async def connect(self):
        if config.DRY_RUN:
            log.info("[DRY_RUN] would connect to %s for device %s", config.ROBOT_WS_URL, config.ROBOT_DEVICE_ID)
            return
        self.ws = await websockets.connect(config.ROBOT_WS_URL, max_size=None)
        handshake = _to_bytes(await self.ws.recv())
        self.own_id = protocol.parse_handshake(handshake)
        if self.own_id is None:
            raise RuntimeError(f"unexpected handshake from relay: {handshake!r}")

        await self.ws.send(protocol.build_packet(protocol.QUERY_DEVICE_HEAD, self.own_id, self.device_id))
        reply = _to_bytes(await self.ws.recv())
        online = protocol.is_device_online(reply)
        if online is not True:
            raise RuntimeError(f"device {config.ROBOT_DEVICE_ID} not online (relay said: {reply!r})")

        self._recv_task = asyncio.create_task(self._recv_loop())
        self._video_request_task = asyncio.create_task(self._video_request_loop())

    async def _video_request_loop(self):
        packet = protocol.build_packet(protocol.REQUEST_VIDEO_HEAD, self.own_id, self.device_id)
        while True:
            await self.ws.send(packet)
            await asyncio.sleep(protocol.REQUEST_VIDEO_INTERVAL_S)

    async def _recv_loop(self):
        async for message in self.ws:
            parsed = protocol.parse_video_chunk(_to_bytes(message), expect_from_id=self.device_id)
            if parsed is None:
                continue
            seq, total, chunk = parsed
            self._frame_chunks[seq] = chunk
            if seq == total:
                ordered = [self._frame_chunks.get(i) for i in range(1, total + 1)]
                if all(c is not None for c in ordered):
                    frame = b"".join(ordered)
                    # The protocol has no frame id, just a per-frame seq/total — if two
                    # frames' chunks interleave (UDP has no ordering guarantee) this can
                    # reassemble garbage that isn't valid JPEG. Only accept it if it has a
                    # proper JPEG SOI/EOI, so a corrupt frame doesn't reach the vision model.
                    if frame[:2] == b"\xff\xd8" and frame[-2:] == b"\xff\xd9":
                        self._latest_frame = frame
                    else:
                        log.warning("discarding malformed frame (%d bytes, bad JPEG markers)", len(frame))
                self._frame_chunks.clear()

    async def get_camera_frame(self, timeout_s: float = 3.0) -> bytes:
        if config.DRY_RUN:
            log.info("[DRY_RUN] would wait for a camera frame")
            with open("test_frame.jpg", "rb") as f:
                return f.read()
        deadline = time.monotonic() + timeout_s
        while self._latest_frame is None:
            if time.monotonic() > deadline:
                raise TimeoutError("no camera frame received from robot")
            await asyncio.sleep(0.05)
        return self._latest_frame

    async def act(self, action: str, magnitude: float = 0.3):
        if action not in ACTION_BODY_KWARGS:
            raise ValueError(f"not a robot action: {action}")
        kwargs = ACTION_BODY_KWARGS[action]
        if action in ARM_ACTIONS:
            hold_ms = max(50, round(config.ARM_HOLD_MS * max(config.ARM_MIN_STRENGTH, magnitude)))
        else:
            hold_ms = max(50, round(config.ACTION_HOLD_MS * max(0.1, magnitude)))

        if config.DRY_RUN:
            log.info("[DRY_RUN] would act %s magnitude=%.2f for %dms", action, magnitude, hold_ms)
            return

        move_body = protocol.encode_control_body(**kwargs)
        move_packet = protocol.build_packet(protocol.ACTION_HEAD, self.device_id, move_body)
        idle_packet = protocol.build_packet(protocol.ACTION_HEAD, self.device_id, protocol.encode_control_body())

        elapsed_ms = 0
        interval_s = config.ACTION_RESEND_INTERVAL_MS / 1000
        while elapsed_ms < hold_ms:
            await self.ws.send(move_packet)
            await asyncio.sleep(interval_s)
            elapsed_ms += config.ACTION_RESEND_INTERVAL_MS
        await self.ws.send(idle_packet)

    async def close(self):
        for task in (self._recv_task, self._video_request_task):
            if task:
                task.cancel()
        if self.ws:
            await self.ws.close()
