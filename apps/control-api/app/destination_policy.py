"""Matching rules for the partner destination allowlist.

Exact `context:extension` entries cover transfers and routes, where the set of
destinations is small and known. Outbound PSTN is different: the number is
chosen per call, so an exact allowlist would need one entry per callee and
nobody can maintain that.

A trailing `*` therefore means "this prefix, then more digits" — an operator
writing `from-trunk:84*` is deliberately allowing Vietnamese numbers through
that context, and nothing else. Only a trailing `*` is a wildcard: dialplan
feature codes such as `*43` and `*97` start with a literal asterisk and must
keep working as exact entries. A prefix rule never matches an empty remainder
and never crosses the `:`, so it cannot widen into another context.
"""

from __future__ import annotations

import re

#: An entry is a context, a colon, and an extension that may end in one `*`.
ENTRY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}:[A-Za-z0-9*#+_-]{1,80}$")

#: The literal part of a prefix rule must be long enough to be a real
#: restriction; `from-trunk:*` would allow the whole dialplan.
MIN_PREFIX_LENGTH = 2


def is_prefix_rule(entry: str) -> bool:
    """True when the entry's extension ends in the wildcard marker.

    Only the final character counts: `*43` is the echo-test feature code, an
    exact destination, while `84*` is a prefix rule.
    """
    _, _, extension = entry.partition(":")
    return extension.endswith("*")


def validate_entry(entry: str) -> None:
    """Raise ValueError when an allowlist entry is malformed or too broad."""
    if not ENTRY_PATTERN.fullmatch(entry):
        raise ValueError("Destinations must use context:extension syntax")
    context, _, extension = entry.partition(":")
    if not extension.endswith("*"):
        # Anything without a trailing asterisk is an exact destination, feature
        # codes like *43 included.
        return
    if len(extension) - 1 < MIN_PREFIX_LENGTH:
        raise ValueError(
            f"'{entry}': a prefix rule needs at least {MIN_PREFIX_LENGTH} literal "
            "characters before the wildcard, otherwise it allows the whole context"
        )
    if not context:
        raise ValueError(f"'{entry}': context is required")


def destination_allowed(context: str, extension: str, allowed: set[str]) -> bool:
    """Decide whether `context:extension` is permitted by the allowlist."""
    target = f"{context}:{extension}"
    if target in allowed:
        return True

    for entry in allowed:
        if not is_prefix_rule(entry):
            continue
        rule_context, _, rule_extension = entry.partition(":")
        if rule_context != context:
            continue
        prefix = rule_extension[:-1]
        # The remainder must be non-empty: `84*` allows 84xxxxxxxxx, not `84`
        # on its own, so a rule can never collapse into a bare context dial.
        if extension.startswith(prefix) and len(extension) > len(prefix):
            return True
    return False
