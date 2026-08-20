#!/usr/bin/env python3
"""Package the partner AI-coding skill into a zip we can hand out.

The checks below are the point of the script. A skill that ships with a
dangling reference, a path only valid inside this repository, or a real-looking
credential is worse than no skill: the partner's assistant will follow it
confidently. Building is the last moment we can catch that, so a failure here
stops the build rather than warning.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "sdks" / "skill" / "connect-asterisk-ai-gateway"
DIST = ROOT / "dist" / "connect-asterisk-ai-gateway-skill.zip"

#: Paths that only resolve inside this repository. A partner's assistant that
#: follows one of these silently reads nothing and invents the rest.
REPO_ONLY = re.compile(r"\b(?:apps|packages|sdks/(?:python|node)|plans|migrations)/")

#: Prefixes of every credential shape that has ever passed through this repo.
SECRET = re.compile(r"\b(?:agw_live_[A-Za-z0-9_]{6,}|npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_-]{20,})")

#: A fixed timestamp keeps the zip byte-identical across rebuilds, so a
#: partner can tell a re-send from a real change.
EPOCH = (2026, 1, 1, 0, 0, 0)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def packaged_files() -> list[Path]:
    files = sorted(
        path
        for path in SKILL.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store"
    )
    if not files:
        fail(f"no files under {SKILL}")
    return files


def check(files: list[Path]) -> None:
    skill_md = SKILL / "SKILL.md"
    if skill_md not in files:
        fail("SKILL.md is missing; an assistant has no entry point without it")

    body = skill_md.read_text()
    for field in ("name:", "description:"):
        if not re.search(rf"^{field}", body, re.M):
            fail(f"SKILL.md frontmatter has no {field.rstrip(':')}")

    for path in files:
        relative = path.relative_to(SKILL).as_posix()
        text = path.read_text(errors="replace")

        found = SECRET.search(text)
        if found:
            fail(f"{relative} contains something shaped like a credential: {found.group()[:12]}…")

        repo_path = REPO_ONLY.search(text)
        if repo_path and path.suffix == ".md":
            fail(f"{relative} points at {repo_path.group()} which does not exist for a partner")

        # A reference nobody is told to read is a reference nobody reads.
        if relative.startswith("references/") and relative not in body:
            fail(f"{relative} is never mentioned in SKILL.md")

    for example in (SKILL / "examples").glob("*.py"):
        compile(example.read_text(), str(example), "exec")


def build(files: list[Path]) -> None:
    DIST.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DIST, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            arcname = Path(SKILL.name) / path.relative_to(SKILL)
            info = zipfile.ZipInfo(arcname.as_posix(), date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> None:
    files = packaged_files()
    check(files)
    build(files)
    print(f"{DIST.relative_to(ROOT)}  ({len(files)} files, {DIST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
