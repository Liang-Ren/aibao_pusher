"""Stage 2 smoke test: connect + send exactly one action, then stop. Use this
to verify each action does what its name says (direction, which servo moves)
before trusting the model to chain them autonomously.

Usage: python test_single_action.py wheel_forward 0.3
"""
import asyncio
import logging
import sys

from robot_client import RobotClient, ACTION_BODY_KWARGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


async def main(action: str, magnitude: float):
    robot = RobotClient()
    print("connecting...")
    await robot.connect()
    print(f"sending {action} magnitude={magnitude}")
    await robot.act(action, magnitude)
    print("done, robot should have stopped")
    await robot.close()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ACTION_BODY_KWARGS:
        print(f"usage: python test_single_action.py <action> [magnitude]")
        print(f"actions: {list(ACTION_BODY_KWARGS)}")
        sys.exit(1)
    action = sys.argv[1]
    magnitude = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
    asyncio.run(main(action, magnitude))
