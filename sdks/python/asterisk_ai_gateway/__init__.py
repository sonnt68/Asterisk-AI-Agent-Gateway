"""Partner SDK for the Asterisk AI Agent Gateway (realtime protocol v1)."""

from .client import (
    DEFAULT_HEARTBEAT_SECONDS,
    PROTOCOL_VERSION,
    Audio,
    GatewayClient,
)
from .errors import (
    AuthenticationError,
    CommandDenied,
    GatewayError,
    ProtocolError,
    RateLimitedError,
)
from .frames import (
    AUDIO_CHANNELS,
    AUDIO_ENCODING,
    AUDIO_SAMPLE_RATE,
    decode_audio_frame,
    encode_audio_frame,
)

__version__ = "0.1.0"

__all__ = [
    "AUDIO_CHANNELS",
    "AUDIO_ENCODING",
    "AUDIO_SAMPLE_RATE",
    "Audio",
    "AuthenticationError",
    "CommandDenied",
    "DEFAULT_HEARTBEAT_SECONDS",
    "GatewayClient",
    "GatewayError",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "RateLimitedError",
    "decode_audio_frame",
    "encode_audio_frame",
]
