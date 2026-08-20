# The partner AI-coding skill

`connect-asterisk-ai-gateway/` is a skill you can hand to a partner so their
AI coding assistant knows how to integrate against this gateway — the
protocol, the audio contract, the scopes, and the mistakes that do not
announce themselves.

It is self-contained: no path in it points back into this repository, so it
works unchanged inside the partner's own codebase.

## Building the zip

```bash
python3 scripts/build_partner_skill.py
```

Writes `dist/connect-asterisk-ai-gateway-skill.zip`. The script refuses to
build if the skill has drifted out of shape — missing frontmatter, a
reference the skill never mentions, a repo-relative path, or anything that
looks like a credential.

## Installing it (for the partner)

Unzip into whichever location the assistant reads:

| Tool | Location |
|---|---|
| Claude Code | `.claude/skills/` in the repo, or `~/.claude/skills/` for every repo |
| Codex / agent harnesses reading `.agents` | `.agents/skills/` |
| Anything else | anywhere; point the assistant at `SKILL.md` |

```bash
mkdir -p .claude/skills
unzip connect-asterisk-ai-gateway-skill.zip -d .claude/skills/
```

The assistant picks it up when the work matches the skill's description. It
can also be invoked by name.

## What to send alongside it

The skill deliberately contains no credentials and no hostname — those are
per-partner and are handed over separately. See
`docs/operations/partner-onboarding.md` for the full handover checklist.
