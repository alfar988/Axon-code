---
name: git-skill
description: Git day to day: branches, commit messages, undoing mistakes (restore, revert, reset, reflog), conflicts, .gitignore, publishing a project to GitHub without leaking tokens, finding a bad commit with bisect.
---
# Git skill

## Quick rules (read first)
1. Look before you act: `git status` and `git diff` before every commit.
2. Commit small, working steps. One reason per commit. Message in the imperative, under 72 characters, saying what and why.
3. Never commit secrets (`.env`, keys, tokens). Check `.gitignore` first.
4. Add files by name (`git add path`), not blindly with `git add -A`, when the folder holds other work.
5. Never force-push a shared branch. Never run `git reset --hard` or `git clean -fd` before checking what would be lost.
6. If a secret was committed, treat it as leaked: rotate it first, then clean the history.

## Safety in this skill
- Do not push to repositories the user does not own or has not named, and do not copy tokens out of credential helpers or config files.
- Do not rewrite history to hide a leaked secret without rotating the secret. Do not commit someone else's private data or code that carries a license you cannot meet.

## Daily loop
```bash
git status -sb                  # what changed, which branch
git diff                        # review unstaged changes; `git diff --staged` for staged ones
git add -p                      # stage hunks on purpose, not everything blindly
git commit -m "Fix crash when the cart is empty"
git switch -c feature/search    # new branch; `git switch main` to go back
git pull --rebase               # update without merge-commit noise
git push -u origin feature/search
```
Commit small, working steps. One reason per commit. Message: imperative, under 72 characters, says what and why ("Retry failed downloads", not "changes" or "fixed stuff"). Add a body when the reason is not obvious.

## Undo recipes
| Situation | Command |
|---|---|
| Discard edits in one file | `git restore path/file` |
| Unstage a file, keep edits | `git restore --staged path/file` |
| Change the last commit message or add a forgotten file | `git add file && git commit --amend` (only before pushing) |
| Undo a pushed commit safely | `git revert <sha>` (creates a new commit) |
| Throw away local commits, match the remote | `git fetch && git reset --hard origin/main` (destructive: check `git status` first) |
| Committed to the wrong branch | `git switch -c right-branch && git switch wrong-branch && git reset --hard HEAD~1` |
| "I lost my commits" | `git reflog` shows every position of HEAD; `git switch -c rescue <sha>` |
| Park work for a minute | `git stash push -m "wip search"` then `git stash pop` |

Never rewrite history that others have pulled (`push --force`); if you must, use `--force-with-lease`.

## Conflicts
`git pull --rebase` stops with conflict markers `<<<<<<<`, `=======`, `>>>>>>>` in the files. Open each file, keep the right combination, delete the markers, then:
```bash
git add path/file
git rebase --continue          # or `git rebase --abort` to go back to where you were
```
Search for leftovers before continuing: `grep -rn "<<<<<<<\|>>>>>>>" .`.

## .gitignore
Create it before the first commit. Common entries:
```
.env
.env.*
!.env.example
node_modules/
__pycache__/
*.pyc
.venv/
dist/
build/
.DS_Store
history/
```
A file that is already tracked stays tracked: `git rm --cached path/file`, then commit.

## Publish a new project to GitHub
```bash
git init -b main
git add . && git commit -m "Initial commit"
# create an empty repository on github.com (no README), then:
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```
Authentication: use the GitHub CLI (`gh auth login`) or an SSH key. A personal access token is entered when git asks for a password; never put it in the remote URL, in files, or in chat. Add a license (`LICENSE`) and a README before sharing.

## A secret was committed
1. Revoke or rotate the secret at the provider first. Deleting it from git is not enough.
2. Remove it from history only if needed (`git filter-repo --path .env --invert-paths`), then force-push.
3. Add the file to `.gitignore`.

## Find the commit that broke it
```bash
git bisect start
git bisect bad                 # current version is broken
git bisect good v1.2.0         # a version that worked
git bisect run python -m unittest      # exit code 0 = good, non-zero = bad; git finds the first bad commit
git bisect reset
```

## Releases
Tag versions `git tag -a v1.2.0 -m "Release 1.2.0" && git push --tags`. Keep a `CHANGELOG.md` (see docs-skill).

## Large files
Git is for text. Keep binaries out (media, datasets, builds); use Git LFS or release assets. Check size before committing: `git count-objects -vH`.

## Good and bad examples

### 1. Commit messages
Bad: `update`, `fix stuff`, `changes`.
Good: `Retry failed downloads up to three times` and, in the body, why a retry was needed.

### 2. What to add
Bad:
```bash
git add -A && git commit -m "done"
```
(this can include `.env`, build output and unrelated edits)
Good:
```bash
git status
git diff
git add src/download.py tests/test_download.py
git commit -m "Retry failed downloads up to three times"
```

### 3. Undo without losing work
Bad: `git reset --hard HEAD~3` to "go back", and the last three commits are gone.
Good: `git switch -c backup-before-undo` first (keeps the commits on a branch), or `git revert <commit>` to undo a change with a new commit.

### 4. A secret was committed
Bad: delete the file in a new commit and carry on. The key is still in history.
Good: revoke and replace the key at the provider first; then remove it from history (for example with `git filter-repo`) only if the user wants that; add the file to `.gitignore`.

### 5. Finding the commit that broke it
Good: `git bisect start`, `git bisect bad`, `git bisect good <old-commit>`, run the test at each step, then `git bisect reset`.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Committed to the wrong branch | `git switch -c new-branch` keeps the commits; then move the old branch back |
| Merge conflict markers left in files | Search for `<<<<<<<`, resolve, run the tests, then commit |
| Huge file rejected by GitHub | Use Git LFS or keep it out of the repo |
| "Author identity unknown" | `git config user.name "..."` and `git config user.email "..."` |
| Pushed by mistake | Do not rewrite shared history; use `git revert` and tell the team |
| Detached HEAD | `git switch -c rescue` to keep the work |

## Checklist before you finish
- [ ] `git status` is clean or shows only what I intend to commit.
- [ ] No secret, key or `.env` is staged.
- [ ] The message says what and why.
- [ ] Nothing destructive was run without a backup branch.
- [ ] I pushed only to the remote and branch the user named.
