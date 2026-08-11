# Git workarounds — local work vs upstream

Simple rules for this machine’s `pysystemtrade` clone. **No rebasing.** Use merge only when bringing in upstream changes.

## Remotes

| Remote | URL | Purpose |
|--------|-----|---------|
| **origin** | `git@github.com:rorymac/pysystemtrade.git` | *Your* fork. Push your work here. |
| **upstream** | `https://github.com/pst-group/pysystemtrade.git` | Original project. Fetch updates from here. **Never push to upstream.** |

Check:

```bash
git remote -v
```

If `upstream` is missing:

```bash
git remote add upstream https://github.com/pst-group/pysystemtrade.git
```

## Branches

| Branch | Role |
|--------|------|
| **my-local-changes** | Day-to-day production branch. All local fixes and WIP live here. |
| **develop** / **master** | Optional mirrors of upstream (for reference). Not required for daily work. |

You normally work on:

```bash
git checkout my-local-changes
```

## What stays out of git

- **`private/`** — gitignored. Account, email, `reporting_directory`, broker settings, etc. live only on this machine.
- **`email.log`** and similar runtime logs — do not commit.
- Secrets (email passwords, API keys) — never commit; keep them in `private/private_config.yaml` only.

Back up `private/private_config.yaml` somewhere outside the repo if you care about disaster recovery (copy, Dropbox, etc.). Git will not save it.

## Preserve local work (commit + push to your fork)

When you have useful code changes you want to keep:

```bash
git checkout my-local-changes
git status
git add path/to/changed/file.py   # only the files you intend to keep
# example for recent report fixes:
# git add sysproduction/data/risk.py \
#         sysproduction/reporting/api.py \
#         sysproduction/reporting/data/risk.py \
#         sysproduction/reporting/formatting.py

git commit -m "Short clear description of what and why"
git push origin my-local-changes
```

That stores history on **your** GitHub fork (`origin`). Upstream is not modified.

Do **not** add:

- `email.log`
- `private/*`
- temp reports under `/home/rorym/data/reports/` (outside the repo anyway)

## Keep local updated from upstream (merge only)

Goal: bring new commits from the original project into `my-local-changes` without rebase and without losing your commits.

### 1. Fetch upstream

```bash
git fetch upstream
```

### 2. Stay on your work branch

```bash
git checkout my-local-changes
```

### 3. Merge upstream into your branch

pst-group active work is usually on **develop**. Prefer that unless you know you want **master**:

```bash
# preferred
git merge upstream/develop

# only if you deliberately track master instead
# git merge upstream/master
```

- If Git reports **conflicts**, fix the listed files, then:

  ```bash
  git add <resolved-files>
  git commit    # completes the merge
  ```

- If the merge is clean, Git may open an editor for a merge message; save and close.

### 4. Push your updated branch to your fork

```bash
git push origin my-local-changes
```

### Full update recipe (copy/paste)

```bash
cd /home/rorym/pysystemtrade
git checkout my-local-changes
git fetch upstream
git merge upstream/develop
# resolve conflicts if any, then commit if needed
git push origin my-local-changes
```

Do this periodically (e.g. when you hear about useful upstream fixes, or every few weeks). Always **commit or stash** your own uncommitted work first so the merge is clean:

```bash
git status   # should be clean, or only files you are happy to include
```

If you have unfinished edits you are not ready to commit:

```bash
git stash push -m "wip before upstream merge"
git fetch upstream
git merge upstream/develop
git push origin my-local-changes
git stash pop   # re-apply your WIP; fix conflicts if any
```

## Mental model

```text
upstream/develop  ── fetch + merge ──►  my-local-changes  ── push ──►  origin/my-local-changes
       ▲                                         │
       │                                         └── your fixes, RM WIP, production tweaks
  pst-group original
```

- **Preserve work** → commit on `my-local-changes`, push to `origin`
- **Update from original** → `fetch upstream` + `merge upstream/develop` into `my-local-changes`
- **Never** force-push to `upstream`
- **Never** rebase (not needed for this workflow)

## Optional: keep a clean upstream mirror

Only if you want a local branch that matches the original, without your custom commits:

```bash
git fetch upstream
git checkout develop
git merge upstream/develop          # or: git reset --hard upstream/develop
git push origin develop             # updates your fork’s develop only
git checkout my-local-changes       # go back to production work
```

Day-to-day trading and cron still use **my-local-changes**.

## Uncommitted work from the reports fix session (reference)

If these are still uncommitted when you next sit down, they are the report/cron fixes worth saving:

| File | Why |
|------|-----|
| `sysproduction/data/risk.py` | Empty instrument list / empty returns no longer crash correlations |
| `sysproduction/reporting/api.py` | Empty `duplicate_instruments` no longer crashes `duplicate_market` report |
| `sysproduction/reporting/data/risk.py` | Empty correlation matrix cluster no-op |
| `sysproduction/reporting/formatting.py` | Account curve x-axis dates (`Jan 2026` style) |

Also local-only (not in git):

- `private/private_config.yaml` → `reporting_directory: /home/rorym/data/reports`  
  (required for PDF reports such as account curve)

## What not to do

| Avoid | Why |
|-------|-----|
| `git rebase` | You asked to keep the workflow simple; merge is enough |
| `git push upstream ...` | You are not the upstream maintainer |
| `git push --force` to shared branches | Can erase history on the remote |
| Committing `private_config.yaml` or email passwords | Secrets and machine paths do not belong in the public fork |
| Working with a dirty tree then merging upstream | Harder conflicts; commit or stash first |

## Quick status check

```bash
git checkout my-local-changes
git status
git log --oneline -5
git remote -v
git fetch upstream
git log --oneline HEAD..upstream/develop | head   # commits you do not have yet (if any)
```

---

*Last updated: 2026-08-11 — merge-only workflow for rorymac fork + pst-group upstream.*
