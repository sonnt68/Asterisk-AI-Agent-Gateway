"""The partner boundary must hold for playback, variables, and dialplan targets."""

import pytest
from app.media_policy import (
    validate_media_uri,
    validate_playback_id,
    validate_variable,
)


class TestMediaUri:
    def test_accepts_asterisk_media_sources(self) -> None:
        assert validate_media_uri("sound:hello-world") == "sound:hello-world"
        assert validate_media_uri("recording:greeting/agent-1") == "recording:greeting/agent-1"

    @pytest.mark.parametrize(
        "media",
        [
            "file:///etc/passwd",          # host filesystem through ARI
            "http://attacker.test/a.wav",  # outbound fetch from the PBX
            "sound:../../../etc/passwd",   # traversal out of the media root
            "sound:hello;rm -rf /",        # shell metacharacters
            "digits:1234",                 # unlisted scheme
            "sound:",                      # empty name
            "nocolon",
            42,
            None,
        ],
    )
    def test_refuses_everything_else(self, media: object) -> None:
        with pytest.raises(PermissionError):
            validate_media_uri(media)


class TestChannelVariable:
    def test_accepts_names_in_the_partner_namespace(self) -> None:
        assert validate_variable("AI_INTENT", "book_flight") == ("AI_INTENT", "book_flight")
        assert validate_variable("AI_SCORE", 7) == ("AI_SCORE", "7")

    @pytest.mark.parametrize(
        "name",
        [
            "CHANNEL(language)",  # dialplan function, i.e. code execution
            "SHELL(rm -rf /)",
            "CDR(userfield)",
            "FILE(/etc/passwd)",
            "AI_",                # prefix with no name
            "MY_VAR",             # outside the partner namespace
            "ai_intent",          # lowercase is not the documented form
            "AI_VAR(x)",
            "",
            None,
        ],
    )
    def test_refuses_names_that_are_not_plain_partner_variables(self, name: object) -> None:
        with pytest.raises(PermissionError):
            validate_variable(name, "value")

    def test_refuses_control_characters_in_values(self) -> None:
        with pytest.raises(PermissionError):
            validate_variable("AI_INTENT", "book\nSet(CHANNEL(x)=y)")

    def test_refuses_oversized_values(self) -> None:
        with pytest.raises(PermissionError):
            validate_variable("AI_INTENT", "x" * 513)

    def test_treats_missing_value_as_empty(self) -> None:
        assert validate_variable("AI_INTENT", None) == ("AI_INTENT", "")


class TestPlaybackOwnership:
    def test_accepts_a_playback_the_call_started(self) -> None:
        assert validate_playback_id("pb-1", {"pb-1"}) == "pb-1"

    @pytest.mark.parametrize("playback_id", ["pb-2", "", None, 7])
    def test_refuses_playbacks_the_call_does_not_own(self, playback_id: object) -> None:
        with pytest.raises(PermissionError):
            validate_playback_id(playback_id, {"pb-1"})
