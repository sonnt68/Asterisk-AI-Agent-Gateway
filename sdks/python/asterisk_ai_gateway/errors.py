"""Errors the gateway can raise at the partner boundary."""

from __future__ import annotations


class GatewayError(Exception):
    """Base class for every SDK failure."""


class GatewayHTTPError(GatewayError):
    """A non-success response from a Gateway HTTP endpoint.

    The exception deliberately keeps only request metadata and the HTTP status.
    Gateway response bodies are not copied into the exception because they may
    contain credentials or other tenant-controlled data.
    """

    def __init__(self, status: int, *, method: str = "GET", path: str = "") -> None:
        self.status = status
        self.status_code = status
        self.method = method
        self.path = path
        super().__init__(f"Gateway {method} {path or 'request'} failed with HTTP {status}")


# Keep the spelling discoverable for callers that use the JavaScript SDK name.
GatewayHttpError = GatewayHTTPError


class AuthenticationError(GatewayError):
    """The API key or realtime token was refused.

    Connection flows retry three times before surfacing this error. A direct
    token request, or a client with reconnect disabled, raises it immediately.
    Check the key and partner app with the gateway operator after exhaustion.
    """


class SessionSupersededError(GatewayError):
    """A newer connection registered this agent slug, so the gateway closed this one.

    The gateway keeps the most recent registration per slug and closes the
    older socket with 4409. The client never reconnects after this: doing so
    would take the slug back and two workers would trade it forever.
    """


class RateLimitedError(GatewayError):
    """Token exchange exceeded the per-key rate limit."""


class ProtocolError(GatewayError):
    """The gateway rejected a frame as invalid for protocol v1."""


class CommandDenied(GatewayError):
    """A control command lacked its scope, or its destination is not allowlisted."""
