"""Prefix rules must widen the allowlist exactly as far as intended, never further."""

import pytest
from app.destination_policy import destination_allowed, validate_entry


class TestEntryValidation:
    @pytest.mark.parametrize(
        "entry",
        [
            "from-internal:1001",
            "from-internal:*43",   # echo test: a literal feature code, not a wildcard
            "from-internal:*97",   # voicemail
            "from-trunk:84*",      # prefix rule
            "ctx_1:100#",
        ],
    )
    def test_accepts_exact_and_prefix_rules(self, entry: str) -> None:
        validate_entry(entry)

    @pytest.mark.parametrize(
        "entry",
        [
            "from-trunk:*",       # the whole context, which is not an allowlist
            "from-trunk:8*",      # one literal character is not a restriction
            "from trunk:84*",     # space in context
            "from-trunk",         # no extension
            ":1001",              # no context
            "",
        ],
    )
    def test_refuses_rules_that_are_malformed_or_too_broad(self, entry: str) -> None:
        with pytest.raises(ValueError):
            validate_entry(entry)


class TestMatching:
    def test_feature_codes_stay_exact_and_do_not_act_as_wildcards(self) -> None:
        allowed = {"from-internal:*43"}
        assert destination_allowed("from-internal", "*43", allowed)
        assert not destination_allowed("from-internal", "*4321", allowed)

    def test_exact_entries_still_match_exactly(self) -> None:
        allowed = {"from-internal:1001"}
        assert destination_allowed("from-internal", "1001", allowed)
        assert not destination_allowed("from-internal", "1002", allowed)

    def test_prefix_rule_matches_longer_extensions(self) -> None:
        allowed = {"from-trunk:84*"}
        assert destination_allowed("from-trunk", "84901234567", allowed)
        assert destination_allowed("from-trunk", "842444501984", allowed)

    def test_prefix_rule_requires_something_after_the_prefix(self) -> None:
        """`84*` must not collapse into dialling `84` itself."""
        assert not destination_allowed("from-trunk", "84", {"from-trunk:84*"})

    def test_prefix_rule_does_not_match_a_different_prefix(self) -> None:
        allowed = {"from-trunk:84*"}
        assert not destination_allowed("from-trunk", "1900123456", allowed)
        assert not destination_allowed("from-trunk", "0084901234567", allowed)

    def test_prefix_rule_never_crosses_into_another_context(self) -> None:
        """The wildcard lives in the extension; it cannot widen the context."""
        allowed = {"from-trunk:84*"}
        assert not destination_allowed("from-internal", "84901234567", allowed)
        assert not destination_allowed("from-trunk-premium", "84901234567", allowed)

    def test_an_empty_allowlist_permits_nothing(self) -> None:
        assert not destination_allowed("from-trunk", "84901234567", set())

    def test_exact_and_prefix_rules_coexist(self) -> None:
        allowed = {"from-internal:1001", "from-trunk:84*"}
        assert destination_allowed("from-internal", "1001", allowed)
        assert destination_allowed("from-trunk", "84901234567", allowed)
        assert not destination_allowed("from-internal", "84901234567", allowed)
