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

- **Always branch from an up-to-date `main`** so the branch's merge-base is
  current — this keeps PR diffs minimal and avoids duplicate/divergent commits:
  ```bash
  git checkout main
  git pull
  git checkout -b <type>/<short-name>   # e.g. feat/saved-routes, fix/cache-count
  # ...work + Conventional Commits...
  git push -u origin <type>/<short-name>
  ```
- Open a PR into `main`. Keep it focused; the description explains what and why.
- **AI agents (Claude) may create branches and PRs but MUST NOT merge a PR** —
  merging is always a human decision. Don't push directly to `main` (it's the
  protected default branch); changes land via PR.

### Merging — squash, with a Conventional Commits PR title

- **Squash-merge** PRs, and make the **PR title** a valid Conventional Commit
  (e.g. `feat: add saved routes`). The squash commit uses the PR title, so the
  release-relevant type lands on `main` exactly once and individual
  work-in-progress commit messages don't pollute history or the changelog.
- This is what drives versioning: a non-conventional title (or a feature whose
  commits aren't `feat:`) means **semantic-release won't cut a release**. If a
  feature reaches `main` without a releasable Conventional Commit, record it
  with an **empty `feat:`/`fix:` commit** (`git commit --allow-empty`) via a PR
  and **merge that one with a merge commit** (squashing an empty commit yields
  nothing to release).

## Local development & tests

- Whole stack: `docker compose up --build` → http://localhost:8900.
- Tests: `make test` (backend Django tests + frontend Vitest). See `README.md`.
- Ops runbooks and the DB schema reference live in `docs/`.

## Suggesting improvements

When you spot a relevant, current best practice (security, CI, testing,
deployment), call it out in the PR or an issue rather than silently changing
unrelated scope.
