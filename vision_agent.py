import base64
import json
import logging

import anthropic

import config
from actions import ACTION_TOOL, SYSTEM_PROMPT

log = logging.getLogger("vision_agent")


class VisionAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def decide(self, task: str, frame_jpeg: bytes, history: list[dict]) -> dict:
        frame_b64 = base64.b64encode(frame_jpeg).decode("ascii")

        history_text = "\n".join(
            f"{i+1}. {h['action']} — {h.get('reasoning', '')}" for i, h in enumerate(history)
        )
        user_text = f"Task: {task}\n\nActions taken so far:\n{history_text or '(none yet)'}"

        resp = self.client.messages.create(
            model=config.VISION_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            tools=[ACTION_TOOL],
            tool_choice={"type": "tool", "name": "robot_action"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": frame_b64},
                    },
                ],
            }],
        )

        for block in resp.content:
            if block.type == "tool_use" and block.name == "robot_action":
                log.info("decision: %s", json.dumps(block.input))
                return block.input

        raise RuntimeError("model did not return a robot_action tool call")
