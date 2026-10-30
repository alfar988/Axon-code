---
name: git-skill
description: Git day to day: branches, commit messages, undoing mistakes (restore, revert, reset, reflog), conflicts, .gitignore, publishing a project to GitHub without leaking tokens, finding a bad commit with bisect.
---
# Git skill

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
