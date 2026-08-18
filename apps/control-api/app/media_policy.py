"""Validation for partner commands that reach past call control into Asterisk.

Playback, channel variables, and dialplan hand-back each hand Asterisk a string
the partner chose. Unvalidated, each is an escape from the partner boundary:

- a media URI of ``file:///etc/passwd`` reads host files through ARI,
- a variable named ``SHELL(...)`` or ``CHANNEL(...)`` is dialplan function
  execution, not a variable assignment,
- a dialplan target outside the allowlist reaches any extension on the PBX.

Everything here fails closed: an input that is not provably safe is rejected
before Asterisk is called.
"""

from __future__ import annotations

import re

#: Media sources a partner may name. `sound:` and `recording:` resolve inside
#: Asterisk's own media directories; every other scheme (`file:`, `http:`,
#: `digits:`, `say:`) is refused because it either reaches the filesystem or
#: takes arbitrary operator input.
ALLOWED_MEDIA_SCHEMES = ("sound", "recording")

_MEDIA_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_-]{0,119}")

#: Variables must be plain names in the partner's own namespace. The `AI_`
#: prefix keeps a partner from overwriting dialplan-critical variables, and
#: rejecting `(` blocks Asterisk dialplan functions, which execute code.
VARIABLE_PREFIX = "AI_"
_VARIABLE_NAME = re.compile(r"AI_[A-Z0-9_]{1,60}")

MAX_VARIABLE_VALUE = 512
_UNSAFE_VALUE = re.compile(r"[\x00-\x1f\x7f]")

#: How many playbacks one call may have running at once.
MAX_PLAYBACKS_PER_CALL = 8


def validate_media_uri(media: object) -> str:
    """Return a safe ARI media URI, or raise PermissionError."""
    if not isinstance(media, str) or ":" not in media:
        raise PermissionError("Media must be a 'sound:name' or 'recording:name' URI")
    scheme, _, name = media.partition(":")
    if scheme not in ALLOWED_MEDIA_SCHEMES:
        raise PermissionError(
            f"Media scheme '{scheme}' is not allowed; use {' or '.join(ALLOWED_MEDIA_SCHEMES)}"
        )
    if ".." in name or not _MEDIA_NAME.fullmatch(name):
        raise PermissionError("Media name contains characters that are not allowed")
    return f"{scheme}:{name}"


def validate_variable(name: object, value: object) -> tuple[str, str]:
    """Return a safe channel variable name and value, or raise PermissionError."""
    if not isinstance(name, str) or not _VARIABLE_NAME.fullmatch(name):
        raise PermissionError(
            f"Variable names must match {VARIABLE_PREFIX}[A-Z0-9_] and cannot be dialplan functions"
        )
    if value is None:
        value = ""
    if not isinstance(value, str | int | float | bool):
        raise PermissionError("Variable value must be a string, number, or boolean")
    text = str(value)
    if len(text) > MAX_VARIABLE_VALUE:
        raise PermissionError(f"Variable value exceeds {MAX_VARIABLE_VALUE} characters")
    if _UNSAFE_VALUE.search(text):
        raise PermissionError("Variable value contains control characters")
    return name, text


def validate_playback_id(playback_id: object, owned: set[str]) -> str:
    """Confirm the partner is stopping a playback its own call started."""
    if not isinstance(playback_id, str) or playback_id not in owned:
        raise PermissionError("Playback is not active on this call")
    return playback_id
