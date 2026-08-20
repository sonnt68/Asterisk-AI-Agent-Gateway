"""The handed-out skill must survive leaving this repository.

A partner's assistant reads it with full confidence and no way to check it
against the source, so the failure mode of a wrong skill is silent wrong code
on their side. These tests guard the properties that make it portable.
"""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "sdks" / "skill" / "connect-asterisk-ai-gateway"

sys.path.insert(0, str(ROOT / "scripts"))
import build_partner_skill as builder  # noqa: E402


@pytest.fixture(scope="module")
def files() -> list[Path]:
    return builder.packaged_files()


class TestItStandsAlone:
    def test_no_reference_points_back_into_this_repository(self, files):
        """`sdks/python` resolves here and nowhere else."""
        for path in files:
            if path.suffix != ".md":
                continue
            found = builder.REPO_ONLY.search(path.read_text())
            assert not found, f"{path.name} references {found.group() if found else ''}"

    def test_every_reference_is_reachable_from_skill_md(self, files):
        body = (SKILL / "SKILL.md").read_text()
        references = [p for p in files if p.parent.name == "references"]
        assert references, "the skill has no references at all"
        for path in references:
            assert f"references/{path.name}" in body

    def test_the_python_example_actually_compiles(self):
        source = SKILL / "examples" / "echo_agent.py"
        compile(source.read_text(), str(source), "exec")


class TestItCarriesNoSecrets:
    def test_nothing_shaped_like_a_credential_ships(self, files):
        for path in files:
            assert not builder.SECRET.search(path.read_text(errors="replace")), path.name

    def test_no_hostname_is_baked_in(self, files):
        """Gateway URLs are per-partner and handed over out of band."""
        literal_host = re.compile(r"https?://(?!gateway\.example\.com)[\w.-]*\d+\.\d+\.\d+\.\d+")
        for path in files:
            assert not literal_host.search(path.read_text(errors="replace")), path.name


class TestTheBuildRefusesBadInput:
    """The checks are the reason to have a build step; prove they can fail."""

    def test_a_credential_stops_the_build(self, tmp_path, monkeypatch):
        leaky = tmp_path / "connect-asterisk-ai-gateway"
        (leaky / "references").mkdir(parents=True)
        (leaky / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\n")
        (leaky / "notes.md").write_text("use agw_live_abcdef123456 to connect\n")
        monkeypatch.setattr(builder, "SKILL", leaky)

        with pytest.raises(SystemExit):
            builder.check(builder.packaged_files())

    def test_an_unmentioned_reference_stops_the_build(self, tmp_path, monkeypatch):
        orphan = tmp_path / "connect-asterisk-ai-gateway"
        (orphan / "references").mkdir(parents=True)
        (orphan / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\n")
        (orphan / "references" / "unread.md").write_text("nobody is sent here\n")
        monkeypatch.setattr(builder, "SKILL", orphan)

        with pytest.raises(SystemExit):
            builder.check(builder.packaged_files())


class TestTheZip:
    def test_it_builds_and_unpacks_under_one_directory(self, tmp_path):
        subprocess.run(
            [sys.executable, "scripts/build_partner_skill.py"], cwd=ROOT, check=True,
            capture_output=True,
        )
        archive = ROOT / "dist" / "connect-asterisk-ai-gateway-skill.zip"
        names = zipfile.ZipFile(archive).namelist()

        # Unzipping into .claude/skills/ must produce exactly one skill dir.
        roots = {name.split("/")[0] for name in names}
        assert roots == {"connect-asterisk-ai-gateway"}
        assert "connect-asterisk-ai-gateway/SKILL.md" in names

    def test_rebuilding_produces_an_identical_archive(self, tmp_path):
        """A partner should be able to tell a re-send from a real change."""
        archive = ROOT / "dist" / "connect-asterisk-ai-gateway-skill.zip"
        first = archive.read_bytes()
        subprocess.run(
            [sys.executable, "scripts/build_partner_skill.py"], cwd=ROOT, check=True,
            capture_output=True,
        )
        assert archive.read_bytes() == first
