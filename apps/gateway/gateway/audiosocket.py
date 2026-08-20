"""Asterisk AudioSocket TLV framing with UUID-before-media enforcement."""

import os
from dataclasses import dataclass
from uuid import UUID

TYPE_TERMINATE = 0x00
TYPE_UUID = 0x01
TYPE_DTMF = 0x03
#: The audio type nominally declares the rate, and the table below records
#: what each value means. Asterisk 21 does not read it that way on the frames
#: it receives: it accepts 0x10 alone and takes the rate from the channel
#: format instead. Both ends therefore have to agree out of band.
TYPE_AUDIO = 0x10
TYPE_AUDIO_SLIN16 = 0x12
TYPE_ERROR = 0xFF

#: Signed-linear audio types Asterisk defines, and the rate each declares.
AUDIO_TYPE_RATES: dict[int, int] = {
    0x10: 8000,
    0x11: 12000,
    0x12: 16000,
    0x13: 24000,
    0x14: 32000,
    0x15: 44100,
    0x16: 48000,
    0x17: 96000,
    0x18: 192000,
}

#: Asterisk 21's res_audiosocket accepts only 0x00 and 0x10 on the frames it
#: reads; sending 0x12 makes it log "message other than hangup or audio" and
#: drop the channel. The rate therefore comes from the channel format the
#: gateway requests when it creates the media channel, and 0x10 is simply
#: "audio" on this version.
GATEWAY_AUDIO_TYPE = TYPE_AUDIO

#: Telephony is 8 kHz from the trunk onwards, so that is what the gateway
#: carries by default. A wider wire does not widen the call: it only inserts
#: resampling steps on either side of the gateway. That cost is real —
#: against an 8 kHz control, a 16 kHz wire put 56% of the agent's energy in
#: the 300-3400 Hz band where the 8 kHz one put 68%, because the partner's
#: 24 kHz source resampled to 16 kHz at a 1.5x ratio its anti-alias filter
#: could not take. Operators bridging genuinely wideband endpoints can raise
#: this; the rate is advertised to the partner in `call.started`.
GATEWAY_SAMPLE_RATE = int(os.environ.get("GATEWAY_MEDIA_SAMPLE_RATE", "8000"))


def channel_format(sample_rate: int) -> str:
    """Asterisk's signed-linear channel format for a sample rate.

    8 kHz is plain `slin`; every wider rate names its kHz, so 16000 is
    `slin16`. This is the string Asterisk parses in the AudioSocket dial
    string's `c(...)`, and it — not the frame type byte — is what tells
    Asterisk how fast to play what arrives.
    """
    if sample_rate not in AUDIO_TYPE_RATES.values():
        raise ValueError(f"Asterisk has no signed-linear format at {sample_rate} Hz")
    return "slin" if sample_rate == 8000 else f"slin{sample_rate // 1000}"

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
        if frame.kind in AUDIO_TYPE_RATES or frame.kind in {
            TYPE_DTMF,
            TYPE_TERMINATE,
            TYPE_ERROR,
        }:
            return None
        raise ValueError("AudioSocket frame type unsupported")
