---
name: create-pr
description: >-
  Stage, commit, push, and open a pull request for the APGuru centralized Alembic
  migrations repo following this project's conventions — branch off `main`, Conventional
  Commits, a single-head + offline-SQL pre-flight (there is no app test suite), and a
  gh-based PR against `main` (which is protected: no direct pushes, owner approval
  required). Use this whenever the user wants to commit changes, push a branch, "ship" /
  "raise" / "open" / "create" / "send up" a PR, or get work reviewed — even if they only
  say "commit this" or "push my changes". Prefer this skill over ad-hoc git commands so
  history stays clean and the protected-main flow is respected.
---

# Create a Pull Request

Turns working-tree changes into a clean, reviewable PR for the **centralized Alembic
migrations** repo — a standalone database-migrations repo with hand-written raw SQL and
**no application code** (see `CLAUDE.md`). The base branch is always **`main`**, which is
**protected by a ruleset**: you cannot push to it directly, and every PR needs the owner's
approving review before it can merge. There is no separate CONTRIBUTING file — this skill
is the team's PR convention, so keep it accurate.

## Golden rules (and why they matter)

- **This skill publishes work.** Committing and pushing are the point — but confirm *what*
  belongs in the PR before you push. Unwinding a wrong push costs more than one question.
- **Never commit to `main` — and you can't push to it anyway.** The ruleset rejects direct
  pushes and requires a reviewed PR. Branch first so every change is reviewable.
- **A migration merge deploys to prod.** Merging to `main` triggers `.github/workflows/
  deploy-prod.yml`, which runs `alembic upgrade head` against the **production** RDS. Treat
  a merge as a real schema change, not just a code merge.
- **Stage deliberately — never blind `git add -A` / `git add .`.** Add explicit paths and
  re-check `git status`; don't sweep in `__pycache__/`, the local `.env`, or editor scratch.
- **Keep secrets and local config out.** `.env` (real DB credentials) and
  `.claude/settings.local.json` are gitignored on purpose. If one shows up staged, you
  forced it — undo it.
- **Never bypass safety.** No `--no-verify`; don't disable or bypass the ruleset.

## Workflow

### 1. Inspect the working tree
```bash
git status
git diff            # unstaged
git diff --staged   # already staged
```
Decide what belongs in *this* PR; if unrelated changes are mixed in, plan to split them.

### 2. Get onto a feature branch
`main` is protected, so branch before committing. This repo names branches
`<type>/<short-topic>`, matching the change's Conventional-Commit type — e.g.
`ci/checkout-v5`, `docs/claude-md`, `feat/add-widget-table`, `fix/duplicate-head`.
```bash
git rev-parse --abbrev-ref HEAD          # confirm current branch
git switch -c <type>/<short-topic>       # only if you're on main
```

### 3. Stage intentionally
```bash
git add <specific paths>
git status                               # verify nothing unexpected is staged
```
Scan the staged list for `.env`, `__pycache__/`, or unrelated files before moving on.

### 4. Pre-flight (the checks that matter here)
There is **no app build/lint/test suite** (`CLAUDE.md`). The gate is migration-chain
sanity — and these need no database:
```bash
alembic heads      # MUST print exactly ONE head — the #1 operational hazard
alembic history    # eyeball the linear chain
```
If your change **adds or edits a migration**, also:
- Preview the SQL offline (no connection needed): `alembic upgrade head --sql`
- If a scratch MySQL is available, prove it reverses: `alembic upgrade <rev>` then
  `alembic downgrade -1`.
- Follow the authoring rules in `CLAUDE.md`: **named SQL parameters only — never
  f-strings**; bare `revision = "NNN"` style (not the typed `script.py.mako` output); keep
  the chain linear and single-headed; write a docstring explaining *why* (intent, hazards).

### 5. Commit with a Conventional Commit message
```
<type>(<scope>): <imperative, lowercase summary>

<body: what changed and — more importantly — WHY. Wrap ~72 columns.>
```
- Imperative subject ("add", "fix", "bump"), not past tense. Prefer small atomic commits.
- For multi-line messages use repeated `-m` flags or `git commit -F <file>` to dodge
  cross-shell quoting pain (teammates are on macOS, Linux, and Windows/PowerShell).
- When Claude Code authors the commit, end with the trailer:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  ```

### 6. Push
```bash
git push -u origin HEAD
```
Updating an existing PR branch after a rebase? `git push --force-with-lease` — never plain
`--force`, which can clobber pushed work.

### 7. Open the PR with `gh`
Target `main`, give it a Conventional-Commits-style title, and write a body a reviewer can
act on. Use `--body-file` (or `-F -`) so multi-line bodies survive any shell:
```bash
gh pr create --base main \
  --title "<type>(<scope>): <summary>" \
  --body-file <path-to-body.md>
```
- Not authenticated? `gh auth status` / `gh auth login`. No `gh`? Share the compare URL
  `git push` prints, or `https://github.com/<owner>/<repo>/compare/main...<branch>?expand=1`.
- End the PR body with:
  ```
  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```
- **The owner must approve before merge** (ruleset). Print the PR URL so the user can review.

### 8. (If enabled) triage automated review bots
If the repo has an automated PR reviewer (e.g. Google's Gemini Code Assist), give it
~60–90s, then fetch and **judge** its comments — apply only verifiable, in-scope
improvements; skip style nitpicks, false positives, and anything that conflicts with
`CLAUDE.md` or that you can't confirm. Never apply a change that would commit a secret or
weaken safety.
```bash
PR=<number>
gh api "repos/{owner}/{repo}/pulls/$PR/comments" --paginate \
  --jq '.[] | select(.user.login|test("gemini";"i")) | {path, line, body}'
gh api "repos/{owner}/{repo}/pulls/$PR/reviews"  --paginate \
  --jq '.[] | select(.user.login|test("gemini";"i")) | {state, body}'
```
Implement accepted ones as a focused follow-up commit, re-run the pre-flight, push to the
same PR, and report what you applied vs. skipped (one-line reason each).

## Commit type reference

| Type | Use for |
|---|---|
| `feat` | A new migration or capability |
| `fix` | Correcting a migration or config bug |
| `ci` | The deploy/migration workflow, runner, or GitHub Actions |
| `chore` | Tooling, deps, non-behavioral cleanup |
| `docs` | Documentation only (README, CLAUDE.md) |
| `refactor` | Behavior-preserving restructuring |

Scopes are optional in this repo; omit them for repo-wide changes. Real examples from
history:
- `ci: bump actions/checkout v4 -> v5 (Node 24)`
- `docs: add CLAUDE.md guidance for Claude Code`
- `feat: make weekly_plan_tasks polymorphic (add task_type, payload, identity key)`

Avoid: `update code` (no type/info), `fixed stuff` (past tense, vague), `feat: WIP`.

## PR body template

```markdown
## Summary
<1–3 sentences: what this PR does and why it exists.>

## Changes
- <key change 1>
- <key change 2>

## Migration safety   <!-- include only when this PR touches alembic/ -->
- [ ] `alembic heads` shows exactly one head
- [ ] chain reviewed (`alembic history`); revision / down_revision correct
- [ ] named SQL params (no f-strings); downgrade hazard noted if lossy
- [ ] note: merging applies this to prod via deploy-prod.yml

## Notes
<follow-ups, breaking changes — or "none">
```

## When the change is bigger than one PR

If the diff spans unrelated concerns, stop and split it — one branch/PR per concern. Small,
focused PRs get reviewed faster and revert cleanly; a grab-bag PR is the most common reason
a review stalls.
