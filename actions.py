from config import SYSTEM_PROMPT  # re-exported for `from actions import ACTION_TOOL, SYSTEM_PROMPT`

ACTION_TOOL = {
    "name": "robot_action",
    "description": "Choose the next single action for the robot to take, based on the camera frame and the task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "wheel_forward", "wheel_backward", "wheel_left", "wheel_right",
                    "done", "give_up",
                ],
            },
            "magnitude": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.3,
                "description": (
                    "How much of the action to apply, 0.0-1.0 (e.g. 0.1 = a small nudge, "
                    "1.0 = a full/large move). Required for all actions except 'done'/'give_up'."
                ),
            },
            "reasoning": {"type": "string", "description": "One short sentence on why this action was chosen."},
        },
        "required": ["action", "reasoning"],
    },
}
