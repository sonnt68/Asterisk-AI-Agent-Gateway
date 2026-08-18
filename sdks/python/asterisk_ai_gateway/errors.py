"""Errors the gateway can raise at the partner boundary."""

from __future__ import annotations


class GatewayError(Exception):
    """Base class for every SDK failure."""


class AuthenticationError(GatewayError):
    """The API key or realtime token was refused.

    Retrying does not help: the key is wrong, revoked, expired, or the
    partner app is disabled. Ask the gateway operator for a new key.
    """


class RateLimitedError(GatewayError):
    """Token exchange exceeded the per-key rate limit."""


class ProtocolError(GatewayError):
    """The gateway rejected a frame as invalid for protocol v1."""


class CommandDenied(GatewayError):
    """A control command lacked its scope, or its destination is not allowlisted."""
