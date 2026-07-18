"""Stage 1 smoke test: connect + fetch one camera frame. Sends no movement
commands, so it's safe to run with the robot sitting anywhere."""
import asyncio
import logging

from robot_client import RobotClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


async def main():
    robot = RobotClient()
    print("connecting...")
    await robot.connect()
    print("connected + device online, waiting for a camera frame...")
    frame = await robot.get_camera_frame(timeout_s=10)
    with open("live_frame.jpg", "wb") as f:
        f.write(frame)
    print(f"got frame: {len(frame)} bytes -> saved as live_frame.jpg")
    await robot.close()


if __name__ == "__main__":
    asyncio.run(main())
