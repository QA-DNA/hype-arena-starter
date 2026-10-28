# Git for the night (beginner-friendly)

Our repo is `github.com/tudsac2308/hype-arena-starter` (a fork of QA-DNA's). Everyone works on their own branch, and the captain merges into `main`. The final pull request goes from our `main` to QA-DNA's repo.

## Once

```powershell
git clone https://github.com/tudsac2308/hype-arena-starter.git
cd hype-arena-starter
git config user.name "Your Name"
git config user.email "you@example.com"
git checkout forge        # or: frontend / engine (the branch you own)
```

If you get "permission denied" on push, the captain hasn't added you yet. They do it under Settings → Collaborators on GitHub, and you accept the email invite.

## Every time you start working

```powershell
git checkout forge          # your branch
git pull origin forge       # get your branch's latest
git merge origin/main       # bring in what the others merged (do this often)
```

## Saving your work (do this often: every working step)

```powershell
git status                  # what changed
git add polygraph/forge.py  # the files you changed (or: git add -A for all)
git commit -m "forge: compare claims convert units"
git push origin forge
```

## Getting your work into main

1. Run `python -m pytest` and `python scripts/eval.py`, and make sure nothing got worse.
2. Push your branch.
3. Tell the captain. They merge it with `git checkout main`, `git merge origin/forge`, `git push`.

## When git says CONFLICT

Two people changed the same lines.

1. Open the file and look for `<<<<<<<`, `=======` and `>>>>>>>`.
2. Keep the right version (or both), and delete the markers.
3. Run `git add <file>`, then `git commit`.
4. If you're unsure, stop and ask the captain. Don't force-push.

## Never

- `git push --force` on `main`.
- Commit `.venv/`, `out/` or `node_modules/` (`.gitignore` already blocks them).
- Push anything to the PR after **11:00 on 29 Oct**. That disqualifies the team.
