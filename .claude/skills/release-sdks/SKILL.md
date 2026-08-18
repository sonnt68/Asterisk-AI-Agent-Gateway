---
name: release-sdks
description: Release the partner SDKs (asterisk-ai-agent-gateway-sdk) to npm and PyPI. Use when asked to publish, release, ship, deploy, or bump a version of the Python or Node SDK, cut a new SDK version, or diagnose a failed SDK publish.
---

# Release the partner SDKs

Both SDKs ship as one package name on two registries, always at the same
version:

| Registry | Package | Source |
|---|---|---|
| npm | `asterisk-ai-agent-gateway-sdk` | `sdks/node` |
| PyPI | `asterisk-ai-agent-gateway-sdk` | `sdks/python` |

The release path is a tag. CI publishes through Trusted Publishing (OIDC), so
no registry token exists in the repository and none should ever be added.

## Preflight

Stop and report if any check fails; never release around a red check.

```bash
git switch main && git pull --ff-only
git status --porcelain                 # must be empty
.venv/bin/ruff check . && .venv/bin/python -m pytest -q
(cd sdks/node && npm test)
```

Confirm the version currently published, so the bump is a real increase:

```bash
curl -s https://registry.npmjs.org/asterisk-ai-agent-gateway-sdk | python3 -c "import json,sys; print('npm ', json.load(sys.stdin)['dist-tags']['latest'])"
curl -s https://pypi.org/pypi/asterisk-ai-agent-gateway-sdk/json | python3 -c "import json,sys; print('pypi', json.load(sys.stdin)['info']['version'])"
```

## Bump both SDKs to the same version

The release workflow refuses to publish when the tag, `pyproject.toml`, and
`package.json` disagree — that guard is the point, so update all three.

```bash
VERSION=0.1.1   # or 0.1.1-rc.1 for a rehearsal

python3 - "$VERSION" <<'PY'
import re, sys
version = sys.argv[1]
p = 'sdks/python/pyproject.toml'
s = open(p).read()
s = re.sub(r'^version = "[^"]+"', f'version = "{version}"', s, count=1, flags=re.M)
open(p, 'w').write(s)

p = 'sdks/node/package.json'
s = open(p).read()
s = re.sub(r'"version": "[^"]+"', f'"version": "{version}"', s, count=1)
open(p, 'w').write(s)
print('bumped to', version)
PY

(cd sdks/node && npm install --package-lock-only --silent)   # keep the lockfile in step
```

Python pre-release syntax differs from npm's: a tag of `sdk-v0.1.1-rc.1`
produces `0.1.1-rc.1`, which hatchling normalises to `0.1.1rc1` on PyPI. That
is expected and does not break the tag guard, which compares the raw strings
in the two manifests.

## Ship it

```bash
git add -A
git commit -m "release: SDKs $VERSION"
git push origin main
git tag "sdk-v$VERSION" && git push origin "sdk-v$VERSION"
gh run watch "$(gh run list --workflow=release-sdks.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

A **pre-release tag** (`sdk-v0.1.1-rc.1`) publishes to TestPyPI only and skips
npm entirely — npm has no staging registry. Use it to rehearse the pipeline
without burning a real version number.

## Verify from the outside

A green workflow is not proof the artifact is usable. Install from each
registry into a throwaway environment:

```bash
cd "$(mktemp -d)"
python3 -m venv v && ./v/bin/pip install -q asterisk-ai-agent-gateway-sdk
./v/bin/python -c "import asterisk_ai_gateway as m; print('pypi ok', m.__version__)"

npm init -y >/dev/null && npm install --silent asterisk-ai-agent-gateway-sdk
node --input-type=module -e "import {GatewayClient} from 'asterisk-ai-agent-gateway-sdk'; console.log('npm ok')"
```

## Registry configuration (one-time, already done)

Trusted publishing is configured for `sonnt68/Asterisk-AI-Agent-Gateway`,
workflow `release-sdks.yml`, environments `npm` / `pypi` / `testpypi`. If a
publish step fails with an OIDC or permission error, re-check that the
environment name in the registry's publisher entry matches the job's
`environment:` value exactly.

## Troubleshooting

Failures seen before, and what they actually mean:

- **npm `E404` on `PUT`** — not a name collision. npm masks permission errors
  as 404. The token or session lacks write access to that package.
- **npm `E403` "Two-factor authentication or granular access token with bypass
  2fa enabled is required"** — the account has no 2FA enrolled at all, or the
  token lacks the bypass flag. Probe with `npm publish --otp=000000`: a real
  2FA account answers `EOTP`/invalid-OTP, an unenrolled one repeats the same
  403.
- **npm 2FA is passkey-only** — npm dropped TOTP authenticator apps, so there
  is no 6-digit code to hand over. WebAuthn needs a browser and biometrics on
  the maintainer's own machine; a manual `npm publish` must be run by them,
  not by an agent. This is exactly why releases go through OIDC instead.
- **npm publish fails while provenance signing succeeded** — the OIDC exchange
  needs npm 11.5.1 or newer, but Node 22 bundles npm 10.x. The workflow
  installs a newer npm before publishing; do not remove that step.
- **npm organisations cannot be created from a token or the CLI** — only the
  website. That is why the package is unscoped rather than
  `@asterisk-ai-agent-gateway/sdk`.
- **PyPI rejects a re-upload of an existing version** — versions are immutable
  and deletion does not free the number. Bump and release again.
- **Tag guard fails** — the tag and the two manifests disagree. Fix the
  manifests, delete the tag (`git push --delete origin sdk-vX.Y.Z`), re-tag.

## Rules

- Never add an npm or PyPI token to the repository, CI secrets, or a config
  file. If someone supplies a token in chat, treat it as compromised: use it
  only if publishing is otherwise blocked, keep it out of every file that git
  tracks, redact it from command output, delete the temporary config
  afterwards, and tell the user to revoke it.
- Never publish from a dirty working tree or a branch other than `main`.
- Never bump one SDK without the other; the two versions move together.
- Report the published URLs and the clean-environment install result. A
  release is not done until an install from the registry has been proven.
