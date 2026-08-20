"""Both bilingual HTML documents must actually be bilingual.

The toggle hides one language wholesale, so a paragraph missing its twin does
not look broken — it looks like the section simply is not there. That failure
is invisible to whoever edits the Vietnamese and never switches to English.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    ROOT / "docs" / "partner" / "integration-guide.html",
    ROOT / "docs" / "operations" / "partner-onboarding.html",
]

VI = re.compile(r'<span class="v">')
EN = re.compile(r'<span class="e">')
PAIR = re.compile(r'<span class="v">.*?</span>\s*<span class="e">', re.S)


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
class TestBothLanguagesAreComplete:
    def test_every_vietnamese_span_has_an_english_twin(self, path):
        body = path.read_text().split("<body>", 1)[1]
        assert len(VI.findall(body)) == len(EN.findall(body))

    def test_the_twin_immediately_follows_its_original(self, path):
        """Order is the contract: the toggle shows whichever is not hidden."""
        body = path.read_text().split("<body>", 1)[1]
        assert len(PAIR.findall(body)) == len(VI.findall(body))

    def test_the_english_half_is_hidden_by_default(self, path):
        """Without this rule both languages render at once."""
        assert ".e { display: none; }" in path.read_text()


class TestTheInternalRunbookSaysSo:
    """It sits one directory from the partner handout and must not be sent."""

    def test_it_is_stamped_internal_in_both_languages(self):
        body = DOCS[1].read_text()
        assert "Nội bộ — không gửi cho đối tác" in body
        assert "Internal — do not send to partners" in body

    def test_it_asks_search_engines_to_stay_away(self):
        assert '<meta name="robots" content="noindex, nofollow">' in DOCS[1].read_text()
