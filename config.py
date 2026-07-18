import os
from dotenv import load_dotenv

load_dotenv()

# IFUUU-4WD cloud relay (see protocol.py). The ESP32 connects out to this over
# UDP; browsers/agents connect over WebSocket and the relay forwards between
# them. Reverse-engineered from the vendor's own server+firmware source
# (ESP32-S3-4WD-V1 package: workerman_4WD.php / code.py / 4wd.php).
ROBOT_WS_URL = os.environ.get("ROBOT_WS_URL", "ws://ifuuu.cn:4609")

# This robot's binding code — the `u` param the vendor App's share link/QR
# uses (16 hex chars = 8 bytes). Identifies *which* device to control/watch.
ROBOT_DEVICE_ID = os.environ.get("ROBOT_DEVICE_ID", "")

# When true (default until a real ROBOT_DEVICE_ID is set), RobotClient logs
# what it would send/expect instead of opening a real WebSocket connection,
# so the vision/decision loop can be developed and tested independently.
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

# How long (ms) to hold each action before auto-sending the stop/idle command.
# The device applies a fixed speed to whatever's non-zero and keeps going
# until told 0 — there's no "move N degrees and stop" primitive — so duration
# is how we translate a discrete action + magnitude into a bounded move.
ACTION_HOLD_MS = int(os.environ.get("ACTION_HOLD_MS", "1000"))
ACTION_RESEND_INTERVAL_MS = 150  # how often to resend while holding, for UDP loss

# Arm/gripper strikes (arm_extend/retract, gripper_loosen/tighten) get their own,
# longer hold + a high minimum strength floor regardless of the model's chosen
# magnitude — these need to be decisive full-range sweeps to actually knock
# something over, not a proportional nudge like the wheels.
ARM_HOLD_MS = int(os.environ.get("ARM_HOLD_MS", "1800"))
ARM_MIN_STRENGTH = float(os.environ.get("ARM_MIN_STRENGTH", "0.8"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
VISION_MODEL = os.environ.get("VISION_MODEL", "claude-sonnet-5")

MAX_STEPS = int(os.environ.get("MAX_STEPS", "30"))
