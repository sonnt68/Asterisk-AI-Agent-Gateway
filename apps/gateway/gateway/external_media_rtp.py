"""ExternalMedia RTP/PCMU adapter for the PCM16 16 kHz gateway contract."""

import asyncio
import struct
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from random import randrange


def ulaw_to_pcm16(payload: bytes) -> bytes:
    samples: list[int] = []
    for encoded in payload:
        value = (~encoded) & 0xFF
        sample = (((value & 0x0F) << 3) + 0x84) << ((value >> 4) & 0x07)
        sample -= 0x84
        if value & 0x80:
            sample = -sample
        samples.extend((sample, sample))
    return struct.pack(f"<{len(samples)}h", *samples)


def pcm16_to_ulaw(payload: bytes) -> bytes:
    samples = struct.unpack(f"<{len(payload) // 2}h", payload)
    encoded = bytearray()
    for index in range(0, len(samples), 2):
        sample = samples[index]
        sign = 0x80 if sample < 0 else 0
        sample = min(abs(sample), 32635) + 0x84
        exponent = min(7, max(0, sample.bit_length() - 8))
        mantissa = (sample >> (exponent + 3)) & 0x0F
        encoded.append((~(sign | (exponent << 4) | mantissa)) & 0xFF)
    return bytes(encoded)


def parse_rtp(packet: bytes) -> bytes:
    if len(packet) < 12 or packet[0] >> 6 != 2:
        raise ValueError("Invalid RTP packet")
    header_length = 12 + (packet[0] & 0x0F) * 4
    if packet[0] & 0x10:
        if len(packet) < header_length + 4:
            raise ValueError("Invalid RTP extension")
        extension_words = int.from_bytes(packet[header_length + 2 : header_length + 4], "big")
        header_length += 4 + extension_words * 4
    if header_length >= len(packet):
        raise ValueError("RTP payload is empty")
    return packet[header_length:]


@dataclass(slots=True)
class RtpState:
    sequence: int = 0
    timestamp: int = 0
    ssrc: int = 0

    def packet(self, payload: bytes) -> bytes:
        header = struct.pack("!BBHII", 0x80, 0, self.sequence, self.timestamp, self.ssrc)
        self.sequence = (self.sequence + 1) & 0xFFFF
        self.timestamp = (self.timestamp + len(payload)) & 0xFFFFFFFF
        return header + payload


class ExternalMediaProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_pcm: Callable[[bytes], Awaitable[None]]) -> None:
        self.on_pcm = on_pcm
        self.transport: asyncio.DatagramTransport | None = None
        self.remote: tuple[str, int] | None = None
        self.rtp = RtpState(ssrc=randrange(1, 2**32))

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.remote = addr
        try:
            pcm = ulaw_to_pcm16(parse_rtp(data))
        except ValueError:
            return
        asyncio.create_task(self.on_pcm(pcm))

    def send_pcm(self, pcm: bytes) -> bool:
        if not self.transport or not self.remote:
            return False
        ulaw = pcm16_to_ulaw(pcm)
        self.transport.sendto(self.rtp.packet(ulaw), self.remote)
        return True

    def close(self) -> None:
        if self.transport:
            self.transport.close()
            self.transport = None
