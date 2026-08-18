"""Scope gate for all partner-initiated call-control commands."""

COMMAND_SCOPES = {
    "audio.clear": "media:control",
    "dtmf.send": "calls:dtmf",
    "call.hold": "calls:hold",
    "call.resume": "calls:hold",
    "call.mute": "calls:mute",
    "call.unmute": "calls:mute",
    "call.hangup": "calls:hangup",
    "transfer.blind": "calls:transfer",
    "transfer.attended": "calls:transfer",
    "transfer.cancel": "calls:transfer",
    "route.queue": "calls:route",
    "route.ring_group": "calls:route",
    "route.voicemail": "calls:route",
    "playback.start": "media:playback",
    "playback.stop": "media:playback",
    "channel.set_var": "channel:variables",
    "dialplan.continue": "calls:dialplan",
    "outbound.originate": "calls:originate",
    "outbound.cancel": "calls:originate",
}


def require_command_scope(command: str, scopes: set[str]) -> None:
    required = COMMAND_SCOPES.get(command)
    if not required:
        raise ValueError("Unsupported call-control command")
    if required not in scopes:
        raise PermissionError(f"Command requires {required}")
