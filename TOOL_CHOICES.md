# Tool choices

Mission Control is a console that has to work 90 minutes before a launch, on
whatever machine the Flight Director's team has in the room, with no time for
an install step, a build step or a service that is down. Each choice below is
tied to that situation, names the alternative that was rejected and why, and
answers the concern Meridian Launch Services would raise first.

## Back end: Python 3 standard library (`http.server`, `sqlite3`, `concurrent.futures`, `urllib`)

**Why this one.** The app has to start on a fresh machine with one command and
no package install. macOS ships Python 3.9 and every Linux control-room image
has Python 3, so `python3 run.py` works with nothing downloaded, which matters
when the network at the pad is restricted and a failed `pip install` would
cost minutes nobody has. The pipeline is small (one sort, three checks, up to
six draft and review calls per report) and the standard library already has a
threaded HTTP server, a thread pool for the three simultaneous checks, an
HTTPS client for the model API and an SQL database. There is no dependency to
pin, audit or lose.

**Rejected alternative: FastAPI with uvicorn and the Anthropic SDK.** It
gives nicer routing, request validation and async calls, but it needs a
virtual environment and about forty packages installed, and the SDK's own
dependency tree changes month to month. A grader or an operator who runs the
start command on a laptop without that environment gets a traceback instead
of a console. The gain in developer comfort does not pay for a single failed
start on launch day.

**Meridian's concern: "Is `http.server` fit for production, or is this a toy?"**
Honest answer: it is fit for this room, not for the public internet. The
server is bound to localhost by default, serves one control room, handles a
few dozen reports an hour and has no login. If Meridian wants it on a shared
network with authentication, TLS and many consoles, the pipeline, storage and
model code are plain modules and can be mounted behind a production server
such as gunicorn or nginx without rewriting them; the HTTP layer is about two
hundred lines and is the only part that would change.

## Front end: plain HTML, CSS and JavaScript served by the back end

**Why this one.** Two pages, no build. The engineer's form and the Flight
Director's console are served as static files by the same process, so a
change is a file edit and a reload, and there is no `npm install`, bundler or
Node version to get right on the console machine. Everything from a report is
placed in the page with `textContent`, which is easy to verify by reading the
two scripts: there is no template engine where an engineer's note could be
interpreted as markup. The console polls the JSON API every ten seconds, which
is fast enough for reports that are briefed in five to thirty minutes.

**Rejected alternative: React with Vite.** Components and state management
would make a larger console easier to grow, but it adds a toolchain, a build
output to commit or to generate, and a second runtime (Node) to the start
command. For two pages that show a queue and a detail panel, the framework
would be most of the code, and a broken build on launch morning is a real way
to lose the console.

**Meridian's concern: "The console will not refresh live, and it looks basic.
Can it scale to a busy count?"** Honest answer: polling is deliberate and
costs one small request every ten seconds; if Meridian wants instant updates
the same JSON endpoints can be pushed over Server-Sent Events from the same
server with no change to the page structure. The look is plain because the
Flight Director needs the verdict badge, the brief-by time and the review
flag readable at a glance from across a desk; styling can be changed in one
CSS file without touching behaviour.

## Database: SQLite, one file

**Why this one.** Reports must survive a restart, and the restart test in the
repository proves they do: the server process is stopped and started again on
the same file and the report is still there. SQLite is in the Python standard
library, needs no server process to be running before the app, and keeps the
whole record of a count (reports, every trace step with its tokens and cost,
briefings and who approved them) in one file that can be copied into the
post-launch review folder. Writes are a few per report, far below what SQLite
handles, and each connection is opened per call so the threaded server is
safe.

**Rejected alternative: PostgreSQL.** It is the right choice for many
consoles across sites with concurrent writers and roles. Here it would mean a
database service that must be installed, started and reachable before
`python3 run.py` works, and a connection string to get right under time
pressure. For one control room and one file, that is risk without benefit.

**Meridian's concern: "A single file on one machine is a single point of
failure. What if the console laptop dies mid-count?"** Honest answer: it is a
single point of failure, and the mitigation is procedural rather than
technical: the file path is an environment variable (`MC_DB_PATH`), so it can
live on a mirrored or network volume, and a copy of the file is a complete
backup that any other machine can open with the same start command. If
Meridian needs live replication across machines, that is the point at which
PostgreSQL becomes worth its setup, and the storage module is the only code
that would change.

## Models: Claude through the Anthropic Messages API, two sizes

**Why this one.** Sorting and the three checks need a fast, cheap model
because they run four times per report and the Flight Director is waiting:
Claude Haiku 5.5 (`claude-haiku-5-5`) returns in a few seconds and costs a
fraction of a cent per call. The draft and review need better judgement and
run up to six times, so they use Claude Opus 5.5 (`claude-opus-5-5`). Every
call sends a JSON schema through structured outputs, so replies are parsed
and validated in code rather than scraped from prose, and the API is called
over plain HTTPS with `urllib` so no SDK is installed. The verdict is never a
model's job: plain code sets it from the three readings before the first
model call, and the models only sort, check and summarise. Prices and model
ids were checked in the Anthropic documentation on 2026-11-12 and are listed
in the README.

**Rejected alternative: a local open-weight model (for example a Llama-class
model through Ollama).** It would remove the dependence on an outside service
and keep notes on the premises, which is attractive. It was rejected because
a console machine in the room would need a multi-gigabyte model download and
enough memory to run it, the draft quality for a crisp briefing is lower, and
the structured-output and refusal handling would have to be built by hand.
The design does leave the door open: every model call goes through one
interface, so a local client is one new module.

**Meridian's concern: "Engineers' notes leave our network, and if the API is
down or slow 90 minutes out, do we lose the console?"** Honest answer, in two
parts. On data: yes, the name, station and note of each report are sent to
Anthropic's API over HTTPS; readings and verdicts are not needed by the model
and are sent only as context. If that is not acceptable, the local-model
option above is the fallback and nothing else in the app changes. On
availability: no. The verdict, violations and brief-by time are computed in
code before any model call, the raw report is saved first, and a failed or
refused call marks the step as an error, falls back to the safe value
(severity high, subsystem unknown, check flagged) and marks the report for
review. The app also starts and runs with no API key at all, with a banner
saying the model steps are simulated, so the console is never the thing that
is down.
