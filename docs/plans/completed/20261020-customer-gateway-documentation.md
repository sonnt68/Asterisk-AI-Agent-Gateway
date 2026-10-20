# Customer Gateway documentation

Date: 2026-10-20

## Status

Completed on 2026-10-20.

## Outcome and authority

User requested customer documentation omit infrastructure product names and
describe integration through Gateway, API, SDK and call signals only.

## Scope

- Customer guides under `docs/partner/`, first-call guide, public SDK readmes,
  and the distributed integration skill and its repository-local mirror.
- Preserve API fields, SDK behavior, scopes, permissions and accurate limits.
- Operator runbooks and application behavior stay outside this wording change.
- User confirmed: remove infrastructure terminology, keep published SDK
  package/import identifiers so installation and examples remain executable.
  Keep existing skill and source-link identifiers accurate as well.
- The preceding call-history question is explanation only: no new API or
  retention policy is authorized by this documentation request.

## Approach and recovery

1. Rewrite infrastructure descriptions as Gateway behavior, remove internal
   setup/CLI instructions, and direct route setup to the Gateway operator.
2. Coordinate non-overlapping HTML and Markdown/skill edits.
3. Check terminology, links, examples, skill packaging, and rendered HTML.
4. Revert only this task's edits if needed; preserve earlier signal changes.

## Progress

- [x] Read authority, customer-document map and affected guides.
- [x] Update customer HTML and Markdown/SDK/skill guidance.
- [x] User confirmed retaining technical package/import identifiers.
- [x] Validate, review and record completion.

## Validation and result

- Existing bilingual and skill-packaging tests: 17 passed.
- Skill `quick_validate.py` passed; distribution rebuilt successfully.
- Terminology scan across 23 customer surfaces passed after allowing exact
  published SDK/import/skill identities and source/registry URLs.
- Relative links and bilingual spans passed for all three HTML guides;
  Markdown relative links passed. Original CSS and language/navigation
  JavaScript are unchanged.
- Python examples compile and pass Ruff; protocol and skill YAML parse;
  `git diff --check` passed. The local skill path is a symlink to the
  distribution source, so it uses the same edits.
- Browser visual inspection unavailable: local-file access was rejected by
  browser URL policy. No alternate route was used to bypass that rejection.
- Independent reviewer found two misleading summaries: status events described
  only as query replies, and an overly broad outbound error diagnosis. Both
  were corrected in both languages; reviewer confirmed resolution and the
  17 tests passed again.

Customer HTML, Markdown, SDK readmes, example wording and integration skill now
describe Gateway-facing behavior. Only approved technical identifiers/links
retain the existing names. The distributable skill archive is ready under
`dist/connect-asterisk-ai-gateway-skill.zip`. Docs impact: minor.

No application deployment, SDK publication, new call-history API, commit or
push performed by this task. Customers can currently maintain their own
list/timeline by persisting `call.status` and `call.ended`; Gateway-hosted
history/list retrieval remains additional product work.
