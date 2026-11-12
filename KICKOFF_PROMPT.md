I'd like you to build a project called Mission Control in this git repository, from an empty repo to a finished, graded submission. It will be marked against the 100-point rubric below, and I want full marks. I also want the commit history to show the app being built step by step, because the history is part of how the work will be read. So please build it in milestones and commit each one as you finish it, rather than writing everything and committing once at the end.

The full problem statement and rubric come first, exactly as I was given them. After that are the decisions I have already made, the places where this project is easy to get subtly wrong, the milestone plan, and what I'd like you to report when you finish.

<problem_statement>
Meridian Launch Services is 90 minutes from a launch. Engineers at the consoles send free-text anomaly reports to the Flight Director, such as a valve that behaved oddly or a telemetry link that dropped. The Flight Director has no time to read raw messages and needs a short, clean briefing for each one.

Build Mission Control, a full stack web app where an engineer files a report, a pipeline reads and sorts it, and the Flight Director approves a drafted briefing.

An engineer files a report with a name, a station, three readings (wind_knots, temp_c, fuel_pct), and a free-text note. Your app then does the following:

- Uses a model to sort the report by subsystem and severity.
- Uses plain code, not a model, to check the readings against the launch limits and set the verdict. Wind must be 25 knots or less, temperature 4 C or more, and fuel 98 to 100 percent. Any reading outside its limit makes the verdict no_go.
- Sets a brief by time of 5, 15, or 30 minutes for high, medium, or low severity. Any limit violation counts as high.
- Runs three model checks at the same time. One looks for hidden instructions in the note, one for missing details, and one for panic in the tone. A note that tries to give the system instructions must never change the verdict.
- Drafts a briefing with a model and has a second model call review it. It repeats up to three rounds.
- Shows the Flight Director the reports, the briefing, the verdict, the cost, and a trace of each step. Only a person can approve a briefing.

You choose your own tools: back end, front end, database, and models.
</problem_statement>

<rubric>
| Criteria | Points | Evidence |
| --- | --- | --- |
| The README has one command to start the app and one to run the tests, and both work | 10 | README in the repo and a run of both commands |
| Tool choices explained. Back end, front end, database, and model are each chosen with a specific reason, one rejected alternative, and one customer concern | 10 | A tool choices file in the repo, either a Word document or a .md file |
| Filing reports. The form sends all fields, bad input is rejected with a clear message, and reports are saved and still there after a restart | 10 | Front end source code and a restart test in the repo |
| Launch limits in plain code. The verdict and violations come from code, not from a model, and are correct exactly on each limit and just past it | 15 | Source code and tests in the repo |
| Brief by time. The time follows severity, and any violation counts as high | 10 | Source code and tests in the repo |
| Sorting with a model. The reply uses a structured schema, is checked in code, and an invalid value falls back safely | 10 | Source code and a test in the repo |
| Three checks and hidden instructions. The checks run at the same time, and a note that gives instructions is flagged, sent to review, and never changes the verdict | 10 | Source code and a test with the hidden instruction note in the repo |
| Draft, review, and approval. The loop stops at three rounds, evaluator feedback goes into the next draft, and only a person can approve a pending briefing | 10 | Source code and tests in the repo |
| Trace and cost. The console shows one card per step with its tokens, and the cost of each report is calculated in code | 10 | Front end source code and cost tests in the repo |
| Tests. The tests pass with no network and no API key, because model calls go through one interface with a fake | 5 | Test run output |
| Total | 100 | |
</rubric>

## How the rubric will be read

Every row names its evidence: a source file, a test, a document, or a command that runs. A grader will look for that specific evidence, so a feature that works but has no test where the rubric asks for one loses points. Treat each row as a claim that needs both the behaviour and the named proof in the repo. The README should end with a table that maps each rubric row to the files and tests that satisfy it, so the grader does not have to hunt.

The first row is worth as much as any feature, and it fails if a grader's machine lacks something. The start command and the test command must each be a single command that works on a fresh clone with no API key set.

## Decisions already made

Use these unless you find a concrete reason they cannot work, in which case tell me before changing course.

- **Back end:** Python, standard library only (`http.server`, `sqlite3`, `concurrent.futures`, `unittest`, `urllib`). A grader then needs only Python 3, with no install step that could fail. Start with `python3 run.py`, test with `python3 -m unittest`. Keep the code compatible with Python 3.9, which is what macOS ships.
- **Front end:** plain HTML, CSS and JavaScript served by the back end, with no build step.
- **Database:** SQLite in a single file, path overridable by an environment variable so tests can use a temporary file.
- **Models:** Claude through the Anthropic Messages API, called over HTTPS. Use a small fast model for sorting and the three checks, and a stronger one for draft and review. Please look up the current model ids and per-token prices in the Anthropic documentation rather than relying on memory, and note in the README the date you checked them.
- **No API key at run time:** when `ANTHROPIC_API_KEY` is absent the app should still start and work, using the fake model, with a visible banner in the console saying model steps are simulated. That keeps the start command working for a grader with no key.

## Where this project is easy to get wrong

These are the parts where a plausible implementation loses points, so they deserve the most care.

**The verdict must be structurally out of a model's reach.** It is not enough to tell the models to ignore instructions in the note. The function that sets the verdict should take the three readings and nothing else, so the note is not even an input. No field of any model reply should be read for the verdict. The verdict, violation and brief-by lines of the final briefing should be written by code, with the model supplying only the summary and recommended action. Text the engineer typed (name and station as well as the note) should reach models inside a clearly delimited block described as data, with any copy of the closing delimiter stripped from it. Then prove it with tests: a hidden-instruction note with out-of-limit readings stays no_go, the same note with in-limit readings stays go, and the verdict is unchanged even when the fake is scripted so that every model reply obeys the note.

**Limits are inclusive, and the tests should sit exactly on them.** 25 knots, 4 C, 98 percent and 100 percent are all go. Test each limit exactly on the value and just past it (25 and 25.01, 4 and 3.99, 98 and 97.99, 100 and 100.01), and test that several violations are all listed. Input validation must not reject out-of-limit readings: a fuel reading of 100.4 is a valid report with a no_go verdict, not bad input. Validation should only reject what cannot be a reading at all, such as text, missing values, or physically absurd numbers.

**"At the same time" needs a test that would fail if the checks ran one after another.** A timing comparison is flaky. A barrier that only releases when all three checks are inside a model call at once is reliable.

**Model replies are checked in code, and failure is safe.** Send a JSON schema with each call, then validate the reply yourself. An invalid severity should fall back to high (brief soonest), an invalid subsystem to an "unknown" value, and the report should be marked for review. A check that errors or returns something unusable should count as flagged. A model call that throws should never lose the report or the verdict; save the raw report before the first model call.

**"Sent to review" should be a real, visible state.** A flagged note should set a needs-review marker with its reason, stored with the report and shown in the Flight Director's queue and on the briefing.

**The draft loop has three things to prove.** It stops after three rounds when the reviewer never passes it; the reviewer's feedback text appears in the next draft's prompt; and it stops early when the reviewer passes. A reviewer reply that is not a real boolean is not a pass.

**Only a person can approve.** The pipeline must have no code path that sets a briefing to approved, even when the model reviewer passes the draft. Approval is its own endpoint, requires a named approver, works only on a pending briefing, and returns a conflict on a second attempt. Test all of that, including that a briefing is still pending straight after the pipeline.

**The restart test should restart something real.** Start the server on a temporary database file, file a report over HTTP, stop the server completely, start a new one on the same file, and read the report back.

**Cost is arithmetic in code.** Each trace step records its model, input tokens and output tokens; cost is tokens times a price table, summed per report. An unknown model id should be priced at the highest known rate so the console never under-reports. The console shows one card per step with its tokens, including the plain-code steps (shown as zero tokens).

**One model interface.** Every model call goes through a single interface with two implementations: the real client and a deterministic fake. The fake should be scriptable per task, including returning bad replies and raising errors, and should record its calls so tests can inspect prompts. No test may construct the real client or touch the network; include one test that blocks non-local connections and runs a full report through the app.

**The engineer's text is untrusted on the screen too.** Render it as text, never as HTML.

**Tool choices need all four parts for all four tools.** Back end, front end, database and model each get a specific reason tied to this situation (a launch console, 90 minutes out), one named alternative with why it was rejected, and one concern the customer, Meridian, would raise, with an honest answer. Generic reasons such as "popular" or "easy to use" will not earn the points.

## Milestones and commits

Work through these in order, using a branch per milestone so the history reads the way a careful engineer's would.

- `main` only ever holds working code: the test command passes and the start command runs at every commit on it. Nothing is committed to `main` directly after the first skeleton commit.
- Start each milestone on a new branch cut from the current `main`, named for its content, such as `feature/launch-limits` or `docs/tool-choices`.
- On the branch, make small commits that each do one thing, with tests in the same commit as the code they cover. A milestone will usually be two to five commits.
- When the milestone is finished and the tests pass, merge it into `main` with `git merge --no-ff` and a merge message that summarises what the milestone added, so each milestone is visible as one unit in `git log --graph`. Then run the tests on `main`, push `main` if a remote is configured, and delete the merged branch.
- If the GitHub CLI is available and signed in, open a pull request for each branch with a short description and merge that with a merge commit instead of merging locally. If it is not, merge locally and do not stop to ask.
- Commit messages say what changed and why in plain language, in the imperative, with a subject line under about 70 characters and a body where the reasoning is not obvious.
- Do not squash, amend, rebase or force-push anything already committed. If a later milestone shows an earlier one was wrong, fix it on a new branch such as `fix/fuel-upper-limit` and say so in the message.
- Add a `.gitignore` in the first commit. The database file, caches, editor files and anything holding an API key must never be committed; check `git status` before each commit rather than using `git add -A` blindly.

1. Project skeleton: a server that serves a placeholder page, the README with the two commands, a first passing test.
2. Launch limits in plain code, with the boundary tests.
3. Brief-by time, with tests.
4. Report validation and SQLite storage, the endpoints to file and read reports, and the restart test.
5. The engineer's report form, with client-side and server-side error messages.
6. The model interface, the fake, and the cost calculation with its tests.
7. Sorting with a structured schema, checked in code, with fallback tests.
8. The three parallel checks and the hidden-instruction tests.
9. The draft and review loop, with tests.
10. Human approval: endpoint, storage and tests.
11. The Flight Director console: queue, briefing, verdict, review flags, cost, and trace cards.
12. The real Anthropic client and the offline banner.
13. The tool choices document and the final README with the rubric table.
14. A last pass against the rubric, fixing anything found.

An honest history with a correction in it is better than a rewritten one.

## Checking your work

Before each commit, run the test command. Before the final commit, do the following and tell me the results.

- Clone the repository into a fresh temporary directory, with `ANTHROPIC_API_KEY` unset, and run both README commands exactly as written.
- File a report through the running app, stop it, start it again, and confirm the report is still there.
- If you have a browser available, open the console, file one clean report and one hidden-instruction report with an out-of-limit reading, approve one, and look at the layout. If you do not, say so.
- If `ANTHROPIC_API_KEY` is set in your environment, run one report through the live models and confirm the structured replies parse and token counts appear. If it is not set, say the live path is untested.
- Read the rubric row by row and, for each, name the file and the test that earns it. Fix any row where you cannot.

## When you finish

Send me a short report: what works and how you confirmed it, anything you could not verify, anything you chose differently from this brief and why, and the output of the final test run. Please be plain about gaps; I would much rather know that the live API path is untested than find out from the grader.
