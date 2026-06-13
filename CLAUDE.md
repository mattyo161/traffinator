# Traffinator — contributor & agent guide

Conventions for working in this repo (humans and AI agents alike). Traffinator
is a containerized commute-time analyzer: Django REST API + React SPA +
PostgreSQL, deployed to Kubernetes via the Helm chart in `deploy/helm/`.

## Commits — Conventional Commits (required)

Every commit message MUST follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <summary>

<optional body>

<optional footer(s)>
```

Common types and their release impact (see Versioning):

| Type | Use for | Version bump |
|---|---|---|
| `feat` | a new feature | **minor** (0.x.0) |
| `fix` | a bug fix | **patch** (0.0.x) |
| `perf` | a performance improvement | patch |
| `docs` | documentation only | none |
| `refactor` | code change, no behavior change | none |
| `test` | tests only | none |
| `build` | build system / dependencies | none |
| `ci` | CI configuration | none |
| `chore` | maintenance | none |

A **breaking change** triggers a **major** bump: add a `!` after the type
(`feat!: ...`) and/or a `BREAKING CHANGE:` footer describing it.

Examples:
```
feat(frontend): add reverse-commute swap button
fix(cache): count Google API calls made before a ZERO_RESULTS failure
docs(runbook): add CSV export runbook
feat(api)!: require ISO timezone in analyze payload

BREAKING CHANGE: the `tz` field is renamed to `timezone`.
```

Branch names follow the same vocabulary: `feat/...`, `fix/...`, `docs/...`,
`chore/...`. PR titles are also Conventional Commits (the squash/merge commit
becomes the release input).

## Versioning — SemVer via semantic-release

Releases are automated. On every push to `main`, `.github/workflows/release.yml`
runs [semantic-release](https://semantic-release.gitbook.io/):

1. analyzes the Conventional Commits since the last release tag,
2. computes the next [SemVer](https://semver.org/) version,
3. creates the git tag `vX.Y.Z` and a GitHub Release with generated notes,
4. triggers the reusable image build so the published GHCR images are tagged
   with that version.

- **Baseline:** `v0.1.0` (already tagged on `main`).
- Pre-1.0.0 semantics: `feat` → minor, `fix`/`perf` → patch, breaking changes →
  minor while in 0.x (semantic-release default). After 1.0.0, breaking → major.
- Config lives in `.releaserc.json`. semantic-release uses `GITHUB_TOKEN` only,
  does **not** commit to `main`, and does **not** publish to npm.
- A release only happens when releasable commits (`feat`/`fix`/`perf`/breaking)
  have landed; docs/chore/ci-only pushes produce no new version.

## Branches & pull requests

- **All changes go through PRs** — never commit directly to `main`
- Branch off `main`, make changes, open a PR
- **AI agents (Claude) may create branches and PRs but MUST NOT merge a PR** —
  merging is always a human decision. Don't push directly to `main` (it's the
  protected default branch); changes land via PR.
- Keep PRs focused; the PR description should explain what and why.

## Local development & tests

- Whole stack: `docker compose up --build` → http://localhost:8900.
- Tests: `make test` (backend Django tests + frontend Vitest). See `README.md`.
- Ops runbooks and the DB schema reference live in `docs/`.

## Suggesting improvements

When you spot a relevant, current best practice (security, CI, testing,
deployment), call it out in the PR or an issue rather than silently changing
unrelated scope.
