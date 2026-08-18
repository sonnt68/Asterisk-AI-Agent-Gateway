import math
import struct

from gateway.external_media_rtp import RtpState, parse_rtp, pcm16_to_ulaw, ulaw_to_pcm16


def test_rtp_pcmu_adapter_preserves_frame_shape_and_signal() -> None:
    source_samples = [int(8000 * math.sin(index / 10)) for index in range(320)]
    source = struct.pack("<320h", *source_samples)
    ulaw = pcm16_to_ulaw(source)
    packet = RtpState(sequence=7, timestamp=160, ssrc=42).packet(ulaw)
    restored = ulaw_to_pcm16(parse_rtp(packet))

    assert len(ulaw) == 160
    assert len(restored) == 640
    assert any(restored)


def test_invalid_rtp_is_rejected() -> None:
    try:
        parse_rtp(b"not-rtp")
    except ValueError as error:
        assert str(error) == "Invalid RTP packet"
    else:
        raise AssertionError("Invalid RTP packet was accepted")
