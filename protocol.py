"""Wire protocol for the IFUUU-4WD relay (ws://ifuuu.cn:4609 <-> UDP device).

Reverse-engineered from the vendor's own server/firmware source
(ESP32-S3-4WD-V1 package): PHP relay (workerman_4WD.php), CircuitPython
firmware (code.py), and the browser control page (4wd.php). All packets are
`head + checksum_byte + body`, checksum = sum(body) & 0xFF.
"""

HANDSHAKE_LEN = 11  # 0x9F, 0x21, checksum, 8-byte assigned client id

QUERY_DEVICE_HEAD = bytes([0x7F, 0x77, 0x78, 0x79])
DEVICE_ONLINE = bytes([0xAF, 0x15, 0x14, 0x13, 0x12])
DEVICE_OFFLINE = bytes([0xBF, 0x19, 0x18, 0x17, 0x16])

REQUEST_VIDEO_HEAD = bytes([0x23, 0x24, 0x25, 0x26])
REQUEST_VIDEO_INTERVAL_S = 5  # matches the vendor page's timerId_B

ACTION_HEAD = bytes([0x43, 0x44, 0x45, 0x46])

VIDEO_FRAME_HEADER = bytes([0x3F, 0x11, 0x23, 0x45, 0x09, 0x08, 0x07, 0x06])
VIDEO_HEADER_LEN = len(VIDEO_FRAME_HEADER)  # 8
DEVICE_ID_LEN = 8  # bytes (16 hex chars)


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def build_packet(head: bytes, *parts: bytes) -> bytes:
    body = b"".join(parts)
    return head + bytes([checksum(body)]) + body


def parse_handshake(data: bytes) -> bytes | None:
    """Returns the 8-byte client id the relay assigned us, or None."""
    if len(data) == HANDSHAKE_LEN and (data[0] == 0x9F or data[1] == 0x21):
        if checksum(data[3:]) == data[2]:
            return bytes(data[3:])
    return None


def _signed_pair(value: float) -> bytes:
    """value in [-1.0, 1.0] -> (sign_byte, magnitude_byte 0-100), matching
    the vendor page's `convert()`: sign 0x00 = negative, 0x01 = positive/zero."""
    magnitude = min(100, round(abs(value) * 100))
    sign = 0x01 if value >= 0 else 0x00
    return bytes([sign, magnitude])


def encode_control_body(
    joystick_x: float = 0.0,
    joystick_y: float = 0.0,
    gripper: int = 0x00,       # slider1: 0x00 idle, 0x01 loosen (放松), 0x02 tighten (抓紧)
    gripper_rotate: int = 0x00,  # slider2: 0x00 idle, 0x01 left, 0x02 right (unused by our action set)
    arm_lift: int = 0x00,     # slider3: 0x00 idle, 0x01 up, 0x02 down (unused by our action set)
    arm_reach: int = 0x00,    # slider4: 0x00 idle, 0x01 extend (往前), 0x02 retract (往后)
    reset: bool = False,      # circle1: reset all servos to their default angle
) -> bytes:
    x_sign, x_mag = _signed_pair(joystick_x)
    y_sign, y_mag = _signed_pair(joystick_y)
    return bytes([
        x_sign, x_mag, y_sign, y_mag,
        gripper, gripper_rotate, arm_lift, arm_reach,
        0x01 if reset else 0x00,
    ])


def is_device_online(data: bytes) -> bool | None:
    if bytes(data[:5]) == DEVICE_ONLINE:
        return True
    if bytes(data[:5]) == DEVICE_OFFLINE:
        return False
    return None


def parse_video_chunk(data: bytes, expect_from_id: bytes):
    """Parse one relayed video packet. Returns (seq, total, chunk_bytes) or
    None if this isn't a matching video frame chunk."""
    header_end = VIDEO_HEADER_LEN
    from_end = header_end + DEVICE_ID_LEN
    to_end = from_end + DEVICE_ID_LEN
    if len(data) <= to_end + 3:
        return None
    if bytes(data[:header_end]) != VIDEO_FRAME_HEADER:
        return None
    from_id = bytes(data[header_end:from_end])
    if from_id != expect_from_id:
        return None
    seq, total, chunk_checksum = data[to_end], data[to_end + 1], data[to_end + 2]
    chunk = bytes(data[to_end + 3:])
    if checksum(chunk) != chunk_checksum:
        return None
    return seq, total, chunk
