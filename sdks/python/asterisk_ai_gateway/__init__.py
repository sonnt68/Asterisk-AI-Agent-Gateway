"""Partner SDK for the Asterisk AI Agent Gateway (realtime protocol v1)."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

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
    DEFAULT_AUDIO_SAMPLE_RATE,
    decode_audio_frame,
    encode_audio_frame,
)

# Read from installed metadata so the constant can never drift from the
# distribution version the way a hand-maintained string does.
try:
    __version__ = _distribution_version("asterisk-ai-agent-gateway-sdk")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0.0.0.dev0"

__all__ = [
    "AUDIO_CHANNELS",
    "AUDIO_ENCODING",
    "AUDIO_SAMPLE_RATE",
    "DEFAULT_AUDIO_SAMPLE_RATE",
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
