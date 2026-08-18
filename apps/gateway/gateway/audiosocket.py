"""Asterisk AudioSocket TLV framing with UUID-before-media enforcement."""

from dataclasses import dataclass
from uuid import UUID

TYPE_TERMINATE = 0x00
TYPE_UUID = 0x01
TYPE_DTMF = 0x03
TYPE_AUDIO = 0x10
TYPE_ERROR = 0xFF
MAX_PAYLOAD_BYTES = 4096


@dataclass(frozen=True, slots=True)
class AudioSocketFrame:
    kind: int
    payload: bytes


def encode_frame(kind: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("AudioSocket payload exceeds gateway frame limit")
    return bytes([kind]) + len(payload).to_bytes(2, "big") + payload


def decode_frame(data: bytes) -> AudioSocketFrame:
    if len(data) < 3:
        raise ValueError("AudioSocket frame header incomplete")
    length = int.from_bytes(data[1:3], "big")
    if length > MAX_PAYLOAD_BYTES or len(data) != length + 3:
        raise ValueError("AudioSocket frame length invalid")
    return AudioSocketFrame(data[0], data[3:])


class AudioSocketHandshake:
    def __init__(self) -> None:
        self.call_uuid: str | None = None

    def accept(self, frame: AudioSocketFrame) -> str | None:
        if self.call_uuid is None:
            if frame.kind != TYPE_UUID or len(frame.payload) != 16:
                raise ValueError("AudioSocket requires a UUID handshake before media")
            self.call_uuid = str(UUID(bytes=frame.payload))
            return self.call_uuid
        if frame.kind in {TYPE_AUDIO, TYPE_DTMF, TYPE_TERMINATE, TYPE_ERROR}:
            return None
        raise ValueError("AudioSocket frame type unsupported")
