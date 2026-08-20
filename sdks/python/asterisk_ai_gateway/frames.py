"""Binary audio envelope for realtime protocol v1.

Every audio frame is the 16 raw bytes of the gateway call UUID followed by
mono PCM samples. Nothing else may be prepended: the gateway routes on those
first 16 bytes.

The encoding and rate of those samples are not fixed by this module. The
gateway announces them per call in `call.started`'s `media` block, because a
deployment bridging plain telephony carries 8 kHz while one bridging wideband
endpoints carries more. Read them from the event; the constants below are only
the common default.
"""

from __future__ import annotations

from uuid import UUID

UUID_BYTES = 16

#: The usual media format, and what to assume when a deployment has not said
#: otherwise. `CallStarted.media` is authoritative.
AUDIO_ENCODING = "pcm_s16le"
DEFAULT_AUDIO_SAMPLE_RATE = 8000
#: Deprecated alias kept so existing partner code keeps importing cleanly.
AUDIO_SAMPLE_RATE = DEFAULT_AUDIO_SAMPLE_RATE
AUDIO_CHANNELS = 1


def encode_audio_frame(call_id: str | UUID, pcm: bytes) -> bytes:
    """Wrap PCM audio for `call_id` in the protocol v1 envelope."""
    if not pcm:
        raise ValueError("Audio frame needs PCM payload after the call UUID")
    identifier = call_id if isinstance(call_id, UUID) else UUID(str(call_id))
    return identifier.bytes + pcm


def decode_audio_frame(frame: bytes) -> tuple[str, bytes]:
    """Split a binary frame into its call UUID string and PCM payload."""
    if len(frame) <= UUID_BYTES:
        raise ValueError("Binary audio frame is too short to carry PCM")
    return str(UUID(bytes=frame[:UUID_BYTES])), frame[UUID_BYTES:]
