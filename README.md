# Mission Control

Meridian Launch Services is 90 minutes from a launch. Engineers at the
consoles file free-text anomaly reports; a pipeline sorts each one, plain
code checks the readings against the launch limits and sets the go / no_go
verdict, three model checks run at the same time, a model drafts a briefing
that a second model call reviews, and the Flight Director approves the
briefing from a console that shows the verdict, the cost and a trace of every
step.

Python 3.9 or later, standard library only. Nothing to install.

## Start the app

```
python3 run.py
```

Then open http://127.0.0.1:8000/ for the engineer's form and
http://127.0.0.1:8000/console for the Flight Director console.

Without `ANTHROPIC_API_KEY` the app still starts and works: model steps use
the built-in deterministic fake and both pages show a banner saying so. With
the key set, model steps call the Anthropic API.

## Run the tests

```
python3 -m unittest
```

The tests never touch the network and need no API key. One test blocks every
non-loopback socket connection while a full report is filed and approved over
HTTP; another starts the server as a real child process, files a report, stops
the process, starts a new one on the same database file and reads the report
back.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | unset | When set, model steps are live; when unset, the fake is used and the console shows a banner. |
| `MC_PORT` | `8000` | Port to listen on. `0` picks a free port and prints it. |
| `MC_HOST` | `127.0.0.1` | Interface to bind. |
| `MC_DB_PATH` | `mission_control.db` | SQLite file. Tests use a temporary file. |
| `MC_FAST_MODEL` | `claude-haiku-5-5` | Model for sorting and the three checks. |
| `MC_STRONG_MODEL` | `claude-opus-5-5` | Model for the draft and the review. |

## Models and prices

Model ids and prices were checked in the Anthropic documentation on
**2026-11-12** (`mission_control/config.py`, `mission_control/pricing.py`).
Prices are US dollars per million tokens.

| Role | Model id | Input | Output |
| --- | --- | --- | --- |
| Fast: sort and three checks | `claude-haiku-5-5` | $0.10 ($0.50 for prompts over 100K tokens) | $0.50 ($2.50 over 100K) |
| Strong: draft and review | `claude-opus-5-5` | $4.00 | $20.00 |
| Also priced | `claude-sonnet-5-5` | $2.00 | $10.00 |
| Also priced | `claude-fable-5-2` | $8.00 | $40.00 |

An unknown model id is priced at the highest rate in the table so the console
never under-reports. Plain-code steps record zero tokens and cost nothing.

Calls go to `POST https://api.anthropic.com/v1/messages` over `urllib` with
`anthropic-version: 2026-10-21`. Every call sends a JSON schema in
`output_config.format` and sets `output_config.effort` (`low` for the fast
model, `medium` for the strong one, which is that model's default stated
explicitly). The strong-model calls opt into server-side refusal fallbacks.
A refusal, a reply cut off at `max_tokens`, or a non-JSON reply is treated as
a failed call; 429, 5xx and network errors are retried once.

## How a report flows

1. `POST /api/reports` validates the six fields. Only input that cannot be a
   reading is rejected (text, blanks, NaN, absurd numbers); out-of-limit
   readings such as fuel at 100.4 percent are valid and produce a no_go.
2. The raw report is saved before any model call.
3. `limits.check_limits(wind_knots, temp_c, fuel_pct)` sets the verdict and
   lists violations. It takes the three readings and nothing else; limits are
   inclusive (25 knots, 4 C, 98 to 100 percent are all go).
4. The fast model sorts the report by subsystem and severity against a JSON
   schema; the reply is validated in code. An invalid severity falls back to
   high, an invalid subsystem to unknown, and the report is marked for review.
5. Code sets the brief-by time: 5, 15 or 30 minutes for high, medium or low;
   any violation counts as high.
6. Three fast-model checks run at the same time in a thread pool: hidden
   instructions, missing details, panic in the tone. A flagged, erroring or
   unusable check adds a review reason. None of them can touch the verdict.
7. The strong model drafts a summary and recommended action and a second call
   reviews it, up to three rounds; the reviewer's feedback goes into the next
   draft prompt; only the JSON boolean `true` is a pass.
8. Code writes the briefing: the verdict, violation and brief-by lines come
   from code, the model supplies only the summary and recommended action. The
   briefing is saved **pending**.
9. Every step appends a trace row with its kind, model, tokens, cost, status
   and duration. Cost is tokens times the price table, summed per report.
10. A person approves the briefing with `POST /api/briefings/<id>/approve`
    and `{"approver": "name"}`. The pipeline has no code path that approves.

Everything an engineer typed (name, station, note) reaches a model only
inside a delimited block described as data, with any copy of the closing
delimiter removed. In the browser it is rendered with `textContent` only.

## API

| Method and path | Purpose |
| --- | --- |
| `GET /` | Engineer's report form |
| `GET /console` | Flight Director console |
| `GET /api/status` | `{simulated, fast_model, strong_model, prices_checked_on}` |
| `POST /api/reports` | File a report; runs the pipeline; `201` with report, briefing, trace and cost, or `400 {"errors": {field: message}}` |
| `GET /api/reports` | Queue, newest first, with verdict, severity, review flag, briefing status and cost |
| `GET /api/reports/<id>` | Full detail: report, briefing, trace steps, cost |
| `POST /api/briefings/<id>/approve` | Approve a pending briefing; `400` without an approver, `404` unknown, `409` if not pending |

## Layout

```
run.py                       start command
mission_control/
  limits.py                  launch limits in plain code
  brief_time.py              brief-by minutes from severity
  validation.py              report validation
  storage.py                 SQLite store (reports, trace steps, briefings, approval)
  model_interface.py         ModelRequest / ModelReply / ModelClient
  fake_model.py              deterministic, scriptable fake
  anthropic_client.py        real client over urllib
  pricing.py                 price table and cost arithmetic
  prompts.py                 data block, schemas and prompt builders
  sorting.py  checks.py  drafting.py  pipeline.py
  server.py                  HTTP routes and static files
  config.py                  model ids and the price check date
static/                      index.html, app.js, console.html, console.js, style.css
tests/                       one module per feature (see the table below)
TOOL_CHOICES.md              back end, front end, database and model choices
```

## Rubric map

| Rubric row | Files | Tests |
| --- | --- | --- |
| README with one start command and one test command, both work | `README.md`, `run.py` | `tests/test_restart.py` runs `run.py` as a child process; `tests/test_server.py` |
| Tool choices explained | `TOOL_CHOICES.md` | |
| Filing reports: form sends all fields, bad input rejected with a clear message, reports survive a restart | `static/index.html`, `static/app.js`, `mission_control/validation.py`, `mission_control/storage.py`, `mission_control/server.py` | `tests/test_form.py`, `tests/test_validation.py`, `tests/test_api.py`, `tests/test_storage.py`, `tests/test_restart.py` |
| Launch limits in plain code, correct exactly on each limit and just past it | `mission_control/limits.py` | `tests/test_limits.py` (25/25.01, 4/3.99, 98/97.99, 100/100.01, all violations listed, readings-only signature) |
| Brief-by time follows severity, any violation counts as high | `mission_control/brief_time.py`, `mission_control/pipeline.py` | `tests/test_brief_time.py`, `tests/test_sorting.py::TestSorting::test_violation_makes_brief_by_five_even_for_low_severity` |
| Sorting with a model: structured schema, checked in code, invalid value falls back safely | `mission_control/prompts.py` (`SORT_SCHEMA`), `mission_control/sorting.py` | `tests/test_sorting.py` |
| Three checks run at the same time; a hidden-instruction note is flagged, sent to review and never changes the verdict | `mission_control/checks.py`, `mission_control/prompts.py` | `tests/test_checks.py` (barrier test, `HIDDEN_NOTE` with fuel 97 stays no_go, in-limit stays go, obedient fake leaves the verdict unchanged) |
| Draft, review and approval: three rounds, feedback into the next draft, only a person approves a pending briefing | `mission_control/drafting.py`, `mission_control/storage.py` (`approve_briefing`), `mission_control/server.py` | `tests/test_drafting.py`, `tests/test_approval.py` |
| Trace and cost: one card per step with its tokens, cost calculated in code | `static/console.js`, `mission_control/pricing.py`, `mission_control/pipeline.py` (`Trace`) | `tests/test_pricing.py`, `tests/test_console.py`, `tests/test_sorting.py::TestSorting::test_trace_has_code_steps_with_zero_tokens` |
| Tests pass with no network and no API key through one model interface with a fake | `mission_control/model_interface.py`, `mission_control/fake_model.py`, `mission_control/anthropic_client.py` | `tests/test_offline.py`, `tests/test_fake_model.py`, `tests/test_anthropic_client.py` (injected transport, no socket) |

## Verification notes

- The test suite was run on Python 3.9.6 (the macOS system Python) and on
  Python 3.14.
- The live API path was **not exercised** during development: no
  `ANTHROPIC_API_KEY` was available in the build environment. The real client
  is covered by tests with an injected transport (request shape, headers,
  schema, usage parsing, refusal, truncation, retries). To check it yourself,
  export the key, start the app and file one report; the trace cards will
  show the live model ids and real token counts.
