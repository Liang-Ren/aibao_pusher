import asyncio
import logging
import sys

import config
from robot_client import RobotClient
from vision_agent import VisionAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("main")


async def run(task: str):
    robot = RobotClient()
    agent = VisionAgent()
    loop = asyncio.get_event_loop()
    history = []

    await robot.connect()
    try:
        for step in range(config.MAX_STEPS):
            frame = await robot.get_camera_frame()
            decision = await loop.run_in_executor(None, agent.decide, task, frame, history)
            history.append(decision)

            action = decision["action"]
            log.info("step %d: %s", step + 1, action)

            if action == "done":
                log.info("task complete")
                return
            if action == "give_up":
                log.warning("model gave up: %s", decision.get("reasoning"))
                return
            await robot.act(action, decision.get("magnitude", 0.3))

        log.warning("reached MAX_STEPS (%d) without finishing", config.MAX_STEPS)
    finally:
        await robot.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python main.py \"<task description>\"")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
