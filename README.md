# aibao_pusher

Vision + LLM autonomy layer for a small 4-wheel differential-drive robot
(ESP32-S3-based, camera mounted low on the chassis), sold under the vendor
brand "IFUUU" (hotspot `IFUUU-4WD`, cloud relay at `ifuuu.cn`). Originally
shipped with a 4-servo arm+gripper (hence the old project name aibao_mover),
but the arm was physically removed — see "Why no arm" below — so this is now
wheels-only: knocking things over means driving into them.

Loop: grab a camera frame from the robot → send it + the task description +
the run's action history to Claude (vision + tool use) → get back one
structured action → execute it on the robot → repeat, until the model
reports `done`.

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
  `ws://ifuuu.cn:4609`. The relay forwards packets between the two sides
  based on 8-byte device/client IDs.
- Every device has a **binding code** (16 hex chars / 8 bytes) — the `u`
  parameter in the vendor App's share link/QR for this robot. Set it as
  `ROBOT_DEVICE_ID`. Ours: `178426002542552D`.
- All packets are `head + checksum_byte + body`, `checksum = sum(body) & 0xFF`.
- **Asymmetric framing**: client→server messages are plain binary, but
  server→client messages are hex-encoded ASCII **text** frames (see
  `4wd.php`'s `hexToBytes()` — easy to miss). `robot_client._to_bytes()`
  handles this on receive.
- **Control is velocity-based, not position-based**: sending a non-zero
  wheel command makes it move at a fixed speed *indefinitely* until you send
  a zero/idle command — there's no "move 30° and stop" primitive. That's why
  `robot_client.act()` sends the command repeatedly for `ACTION_HOLD_MS *
  magnitude` and then auto-sends idle.
- Camera frames arrive as chunked packets relayed over the same WebSocket,
  reassembled by sequence number into a JPEG (`RobotClient._recv_loop`). The
  protocol has no frame ID, so chunks from two frames can interleave under
  UDP reordering — a reassembled frame is only accepted if it has valid JPEG
  SOI/EOI markers, otherwise it's discarded rather than sent to the model.

### Why no arm

The kit's 4-servo arm/gripper (base reach, lift, gripper rotate, grip) is
still fully supported by the wire protocol (`protocol.encode_control_body`),
but the camera was mounted on the arm itself, which caused two persistent
problems: the arm's own structure permanently occluded part of the frame,
and the model had no reliable way to judge the arm's actual reach/contact
point from a single 2D image, so `arm_extend` attempts frequently missed the
target even when well-aimed by eye. The user removed the arm physically;
`actions.py`'s action space is now wheels-only (`wheel_forward/backward/
left/right` + `done`/`give_up`). Re-adding arm actions is straightforward
(the protocol layer already supports it) if a future revision remounts the
camera off the arm.

### Action space (see `actions.py` / `robot_client.py`)

4 actions the model can choose between, each with a magnitude 0.0-1.0:
`wheel_forward`, `wheel_backward`, `wheel_left` (turn in place), `wheel_right`
(turn in place) — this is differential steering, not strafing. Plus `done`
and `give_up` to end the run.

**Untested / needs empirical verification once the real device replies**:
the sign convention for `wheel_left`/`wheel_right` (which physical direction
positive vs. negative joystick-X produces) — inferred from the vendor page's
`getDirection()` angle mapping, not observed on hardware.

### Decision strategy (`SYSTEM_PROMPT`, now in `.env`)

The system prompt lives in `.env` / `.env.example` (see `config.py`) rather
than hardcoded in `actions.py`, so it can be tuned without touching code. It
encodes lessons from testing against the real robot:

- Explicit SEARCH (rotate to find a target) vs. ATTACK (center then ram)
  modes, since the model tends to alternate turn directions indecisively or
  ram off-center without an explicit strategy.
- Center-before-ramming: small alignment nudges before committing to a
  full-force forward drive, re-checked after every move.
- A close-up blurry frame right after approaching a target is treated as
  "target pressed against the camera," not "target disappeared" — otherwise
  the model prematurely `give_up`s.
- Wedged-against-a-wall handling: turn immediately rather than backing up
  first.
- A bounded "done" criterion (2-3 distinct vantage points swept clean) —an
  earlier version asked for an open-ended "confirm nothing's left" check and
  the model just kept re-scanning forever, too cautious to ever stop.

**The model cannot reliably self-track continuous state** (e.g. "how far
have I rotated") from free-text history alone — in practice it would claim
to still be mid-sweep even after 80+ consecutive turn commands in a large
space. `main.py` tracks a real consecutive-turn counter in code and injects
a deterministic system-note into the history once a streak strongly implies
a full rotation was completed without the model noticing, rather than
trusting it to count.

## Files

- `protocol.py` — packet framing, checksums, action encoding, video-chunk parsing
- `config.py` — env-driven settings (relay URL, device id, dry-run, hold duration, system prompt)
- `robot_client.py` — async WebSocket client implementing the protocol above
- `actions.py` — the action schema (Claude tool definition), re-exports `SYSTEM_PROMPT` from `config`
- `vision_agent.py` — one Claude vision+tool-use call: frame + task + history → action
- `main.py` — the async step loop, including the turn-streak nudge and vision-API error recovery
- `test_connection.py` — stage-1 smoke test: connect + fetch one camera frame, no movement
- `test_single_action.py` — stage-2 smoke test: connect + send exactly one action, verify direction

## Run

```
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY and ROBOT_DEVICE_ID
# set DRY_RUN=false once ready to hit the real robot
python main.py "现场有很多瓶子，找到每一个还站立的瓶子撞倒，确认没有站立的瓶子后结束"
```

With `DRY_RUN=true` (the default), nothing touches the network: actions are
logged and `get_camera_frame()` reads a local `test_frame.jpg` — drop a
sample photo there to smoke-test the decision loop before going live.

Before a live run, `python test_connection.py` (verifies the connection and
saves a real frame as `live_frame.jpg`) and `python test_single_action.py
<action> [magnitude]` (verifies one action does what its name says) are
worth running first — cheaper than debugging a bad run 60 steps in.
