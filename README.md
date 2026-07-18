# aibao_mover

Vision + LLM autonomy layer for the aibao_mover robot: a 4-wheel differential-drive
chassis with a single-axis arm/gripper and a camera, ESP32-S3-based, sold under the
vendor brand "IFUUU" (hotspot `IFUUU-4WD`, cloud relay at `ifuuu.cn`).

Loop: grab a camera frame from the robot → send it + the task description to
Claude (vision + tool use) → get back one structured action → execute it on
the robot → repeat, until the model reports `done`.

## Protocol

Reverse-engineered from the vendor's own source, obtained directly from the
seller (`ESP32-S3-4WD-V1` package: `workerman_4WD.php` cloud relay,
`code.py`/`ServoController.py`/`MotorController.py` CircuitPython firmware,
`4wd.php`/`WebSocketClient.js` browser control page — not from packet
sniffing). Full detail in `protocol.py`; summary:

- The ESP32 connects **out** over UDP to `ifuuu.cn:4209`. It never listens
  locally — there's no LAN endpoint to hit, everything goes through the cloud
  relay.
- We (like the browser control page) connect over **WebSocket** to
  `ws://ifuuu.cn:4609`. The relay forwards binary packets between the two
  sides based on 8-byte device/client IDs.
- Every device has a **binding code** (16 hex chars / 8 bytes) — the `u`
  parameter in the vendor App's share link/QR for this robot. Set it as
  `ROBOT_DEVICE_ID`. Ours: `178426002542552D`.
- All packets are `head + checksum_byte + body`, `checksum = sum(body) & 0xFF`.
- **Control is velocity-based, not position-based**: sending a non-zero
  wheel/arm command makes it move at a fixed speed *indefinitely* until you
  send a zero/idle command — there's no "move 30° and stop" primitive. That's
  why `robot_client.act()` sends the command repeatedly for `ACTION_HOLD_MS *
  magnitude` and then auto-sends idle.
- Camera frames arrive as chunked UDP packets relayed over the same
  WebSocket, reassembled by sequence number into a JPEG (see
  `RobotClient._recv_loop`).

### Action space (see `actions.py` / `robot_client.py`)

8 actions the model can choose, each with a magnitude 0.0-1.0:
- wheels (differential steering, not strafing): `wheel_forward` /
  `wheel_backward` / `wheel_left` (turn in place) / `wheel_right` (turn in place)
- arm reach: `arm_extend` / `arm_retract`
- gripper: `gripper_loosen` / `gripper_tighten`

The firmware actually exposes **2 more servo axes** we're deliberately not
using yet: arm up/down (servo 1) and gripper left/right rotation (servo 2).
Wire format already supports them (`arm_lift`, `gripper_rotate` in
`protocol.encode_control_body`) — extend `ACTION_BODY_KWARGS` in
`robot_client.py` and the enum in `actions.py` if/when wanted.

**Untested / needs empirical verification once the real device replies**:
the sign convention for `wheel_left`/`wheel_right` (which physical direction
positive vs. negative joystick-X produces) — inferred from the vendor page's
`getDirection()` angle mapping, not observed on hardware.

## Files

- `protocol.py` — packet framing, checksums, action encoding, video-chunk parsing
- `config.py` — env-driven settings (relay URL, device id, dry-run, hold duration)
- `robot_client.py` — async WebSocket client implementing the protocol above
- `actions.py` — the action schema (Claude tool definition) and system prompt
- `vision_agent.py` — one Claude vision+tool-use call: frame + task + history → action
- `main.py` — the async step loop

## Run

```
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and ROBOT_DEVICE_ID
# set DRY_RUN=false once ready to hit the real robot
python main.py "把桌上的杯子拿到盒子里"
```

With `DRY_RUN=true` (the default), nothing touches the network: actions are
logged and `get_camera_frame()` reads a local `test_frame.jpg` — drop a
sample photo there to smoke-test the decision loop before going live.
