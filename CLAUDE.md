# Mission Control

A graded project for Meridian Launch Services: engineers file anomaly reports, a pipeline sorts them, plain code sets the go / no_go verdict from the launch limits, and the Flight Director approves a drafted briefing. The full brief and rubric are in `KICKOFF_PROMPT.md`. Read it at the start of any session.

## Commands

- Start: `python3 run.py`
- Test: `python3 -m unittest`

Both must work on a fresh clone with no API key and nothing installed. Run the tests before every commit.

## Rules that hold for every change

- Python standard library only, compatible with Python 3.9. No third-party packages, because the grader runs the two commands on their own machine and an install step is a way to lose points.
- The verdict comes from plain code that takes the three readings and nothing else. No model reply and no text from a note may influence it.
- Every model call goes through the single model interface. Tests use the fake and never touch the network.
- Nothing in the pipeline may approve a briefing. Approval happens only through the endpoint a person calls.
- Text typed by an engineer is untrusted: delimit it as data in prompts and render it as text in the page.
- Where the rubric names a test as evidence, the feature is not done until that test exists.

## Commits

The commit history is part of the submission. Build in the milestone order from the brief.

- `main` always works: tests pass and the app starts at every commit on it. No direct commits to `main` after the first skeleton commit.
- One branch per milestone, cut from current `main`, named like `feature/launch-limits`, `fix/...` or `docs/...`.
- Small commits that each do one thing, with tests in the same commit as the code they cover.
- Merge a finished milestone into `main` with `git merge --no-ff` (or a pull request merged with a merge commit, if the GitHub CLI is signed in), run the tests on `main`, push, and delete the branch.
- Plain imperative commit messages that say what changed and why.
- Never amend, squash, rebase or force-push existing commits. Fix mistakes on a new branch.
- Check `git status` before committing. Never commit the database file, caches or anything holding an API key.

## If a session is resumed

Check `git log --graph --oneline --all` and `git branch` against the milestone list to see where the work stopped. If a milestone branch is unmerged, finish it on that branch. Otherwise run the tests on `main` and start the next milestone on a new branch.
