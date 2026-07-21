import asyncio
import logging
import sys

import anthropic

import config
from robot_client import RobotClient
from vision_agent import VisionAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("main")


# The model can't reliably self-track how far it has rotated from free-text
# history alone (in practice it just keeps saying "continue the sweep"
# forever in a large/multi-room space). So we count turns in code instead,
# and inject a deterministic nudge once a streak of consecutive turns strongly
# suggests it has already gone all the way around without noticing.
TURN_ACTIONS = {"wheel_left", "wheel_right"}
FIRST_NUDGE_AFTER = 20
RENUDGE_EVERY = 15

# Similarly, the model reliably *labels* wedged situations in its own reasoning
# ("wedged", "stuck") but in practice keeps retrying the same backward+turn
# combo even after it's clearly not working — this traps it in corners, where
# turning the same direction it was told to favor for SEARCH mode just faces
# it back into the other wall. Count consecutive wedge-labeled steps in code
# and force a direction-switch suggestion rather than trusting it to notice.
WEDGE_KEYWORDS = ("wedged", "stuck")
WEDGE_NUDGE_AFTER = 4


async def run(task: str):
    robot = RobotClient()
    agent = VisionAgent()
    loop = asyncio.get_event_loop()
    history = []
    turn_streak = 0
    next_nudge_at = FIRST_NUDGE_AFTER
    wedge_streak = 0

    await robot.connect()
    try:
        for step in range(config.MAX_STEPS):
            frame = await robot.get_camera_frame()
            try:
                decision = await loop.run_in_executor(None, agent.decide, task, frame, history)
            except anthropic.APIStatusError as e:
                # A single bad/corrupt camera frame (or a transient API error) shouldn't
                # kill a run that's otherwise made real progress — skip this step and
                # try again with a fresh frame next iteration.
                log.warning("step %d: vision call failed (%s), retrying with a fresh frame", step + 1, e)
                continue
            history.append(decision)

            action = decision["action"]
            log.info("step %d: %s", step + 1, action)

            if action == "done":
                log.info("task complete")
                return
            if action == "give_up":
                log.warning("model gave up: %s", decision.get("reasoning"))
                return

            turn_streak = turn_streak + 1 if action in TURN_ACTIONS else 0
            if turn_streak >= next_nudge_at:
                log.info("injecting turn-streak nudge after %d consecutive turns", turn_streak)
                history.append({
                    "action": "SYSTEM_NOTE",
                    "reasoning": (
                        f"You have just made {turn_streak} consecutive turning moves without "
                        "committing to approach anything. That is very likely more than a full "
                        "360 degree rotation already, even if the scenery still looks unfamiliar "
                        "(a large or multi-room space can look different at every angle without "
                        "you having actually missed anything). Stop turning in place: either call "
                        "done if you believe every bottle you've found is down, or drive forward "
                        "to a clearly different vantage point before resuming search."
                    ),
                })
                next_nudge_at = turn_streak + RENUDGE_EVERY

            reasoning_lower = decision.get("reasoning", "").lower()
            if any(kw in reasoning_lower for kw in WEDGE_KEYWORDS):
                wedge_streak += 1
            else:
                wedge_streak = 0
            if wedge_streak >= WEDGE_NUDGE_AFTER:
                log.info("injecting wedge-streak nudge after %d consecutive wedge reports", wedge_streak)
                history.append({
                    "action": "SYSTEM_NOTE",
                    "reasoning": (
                        f"You have reported being wedged {wedge_streak} times in a row without "
                        "escaping. Whatever combination of backing up and turning you've been "
                        "using is not working here — you are very likely in a corner, not against "
                        "a flat wall, so repeating the same turn direction just faces you into the "
                        "other wall each time. Switch to turning the OPPOSITE direction from what "
                        "you've been using, and back away further (magnitude 0.6+) before that "
                        "turn."
                    ),
                })
                wedge_streak = 0

            await robot.act(action, decision.get("magnitude", 0.3))

        log.warning("reached MAX_STEPS (%d) without finishing", config.MAX_STEPS)
    finally:
        await robot.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python main.py \"<task description>\"")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
