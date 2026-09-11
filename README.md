# OpenXC — Cross Country Race Timing

A self-contained, containerized application for running cross country meets:
manage meets and races, maintain rosters, record finish order live on race
day, and publish team scoring + individual results to a public results page.

- **Backend**: Python + FastAPI, SQLAlchemy, Alembic migrations
- **Frontend**: SvelteKit dashboard
- **Database**: PostgreSQL
- **Tag stream / events / starter**: Valkey (Redis-compatible) + small Go services
- **Deployment**: Docker Compose (runs equally well on a laptop or a
  Raspberry Pi / other ARM64 board)

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- **Dashboard**: http://localhost (passcode-protected — default `1234`, see
  [Dashboard passcode](#dashboard-passcode))
- **API docs**: http://localhost:8000/docs

On first boot, migrations run automatically and (by default) a demo meet
("Riverside Invitational (Demo)") is seeded with three races, rosters for
five teams, and sample finish results, so you have something to click
around immediately. Disable this by setting `SEED_DEMO_DATA=false` in `.env`
before the first `docker compose up`.

To access the app from another device on your network (e.g. viewing the
public results page on a phone while the app runs on a laptop or Pi),
use that machine's LAN IP or hostname instead of `localhost`, e.g.
`http://raspberrypi.local`. nginx and the frontend both proxy API calls
through themselves, so no extra configuration is needed for this to work.

Meets are identified by a readable slug rather than an opaque ID, so URLs
stay shareable and memorable: `"Really Big Invitational"` with a date in
2026 becomes `really_big_invitational_2026`, used everywhere a meet ID
appears (`/meets/{id}`, `/results/{id}`, `/api/meets/{id}`). The slug is
derived from the meet name and the year of its date (or the current year if
no date is set) at creation time, and stays fixed after that even if you
rename the meet later — so a results link you've shared keeps working. If
the same name + year is used twice, later meets get a `-2`, `-3`, … suffix.

Races get the same treatment, scoped to their meet: `"Boys Varsity"` becomes
`boys_varsity`, giving every race its own public results page at
`/{meet_slug}/{race_slug}` — e.g. `/really_big_invitational_2026/boys_varsity`.
It's linked from both the dashboard's Results tab and the meet's public
results page ("Race page ↗" next to each race).

## Architecture

```
docker-compose.yml
├─ postgres   — durable storage, named volume `postgres_data`
├─ valkey     — tag-read stream + pub/sub (port 6379, published for diagnostics)
├─ backend    — FastAPI REST API (port 8000, also reachable directly), runs Alembic migrations on boot
├─ frontend   — SvelteKit app (internal only), server-side proxies /api/* to backend
├─ events     — thin SSE bridge onto Valkey pub/sub (internal only, see events/server.go)
├─ nginx      — reverse proxy (port 80): / → frontend, /api → backend, /events → events
└─ starter    — optional; watches a host trigger file and posts start events (see starter/README.md)
```

nginx is the app's main entry point: it listens on port 80 and routes `/`
to the frontend, `/api` to the backend, and `/events` to the SSE bridge (see
`nginx/default.conf`), so the browser only ever needs one origin and one
port. This means the app works from any hostname/IP without rebuilding —
handy when moving the same images between a laptop and a Pi, or between
wifi networks on race day.

The frontend also proxies `/api/*` to the backend itself (see
`frontend/src/hooks.server.js`), which is what makes `npm run dev` outside
Docker work the same way. Through nginx this second hop isn't used, since
nginx already routes `/api` straight to the backend.

The backend's own port stays published too (`BACKEND_PORT`, default 8000),
mainly for the interactive API docs at `/docs` — nginx only proxies paths
under `/api`, not `/docs` — and as a convenience for external tools that
want to talk to the API directly (see [API](#api) below).

## Usage flow

1. **Create a meet** — sidebar → "New Meet". Give it a name, date, and
   location. Each meet in the sidebar list also has a toggle for marking it
   the **active** meet — at most one meet is active at a time (setting one
   deactivates whichever was active before). This exists for external
   devices/scripts (like the [starter module](starter/README.md)) that
   shouldn't need to know a meet's id: they can POST to the meet-agnostic
   `/api/starts` and `/api/finishes` endpoints (see [API](#api)), which
   resolve to whatever meet is currently toggled active, instead of the
   meet-scoped `/api/meets/{meet_id}/...` versions.
2. **Add teams** — **Teams** tab. Enter the teams/schools invited to the
   meet one at a time, or use **Bulk Add** to paste a list of names (one per
   line). Teams are meet-scoped, so the same school across two meets is two
   separate entries — this is what powers the team dropdown everywhere else.
3. **Add races** — **Races** tab → "Add Race". Each race has its own scoring
   configuration: number of scoring athletes (typically 5) and number of
   displacers (typically 2). Each race card also tracks its own gun-to-finish
   timing — see step 5.
4. **Add athletes** — **Athletes** tab. Add one at a time (team and race are
   dropdowns populated from the Teams/Races tabs), or use **Bulk Import** to
   paste a whole roster (`bib, first, last, team, grade, race name` — one
   per line, comma or tab separated). A team or race name that doesn't match
   an existing one falls back to the default team/race you pick for the
   import — handy when most of a pasted roster is one team. Athletes are
   unique per meet by bib number. Select multiple rows with the checkboxes
   to bulk-reassign them to a different team and/or race at once.
5. **Start each race** — on the **Races** tab, each card shows a status
   (Not Started / Started / Finished) and a live elapsed-time clock. Click
   **Start** to open the start dialog: either pick a submitted start (the
   gun) from the list, or enter how long ago the race actually started —
   `120` for seconds, or `2:00` for minutes:seconds — which backdates the
   start time by that much. Leave it at `0` if the gun is going off right
   now. This is built for timing with a stopwatch at the line and entering
   the elapsed time once you're back at the computer, rather than needing to
   be at the keyboard the instant the gun fires. Once started, the clock
   counts up live from that start time; flip the **Finish**
   toggle to freeze it and mark the race finished, or flip it back off to
   keep timing. Made a mistake on the start time? **Reset** clears both the
   start and finish time (after a confirmation) so you can run the start
   dialog again — it only touches timing, recorded finishers and results are
   untouched. Starts themselves come from `POST /api/meets/{meet_id}/starts`
   or, for a device that doesn't know the meet id, `POST /api/starts` (which
   resolves to whichever meet is toggled **active** in the sidebar — see
   step 1 and [API](#api)) — an external starter device/app can submit one
   directly, and it shows up in the dialog's list for any race to use.
6. **Time the race** — **Time Entry** tab. Optionally start the race clock,
   then record finishers as they cross the line by typing/scanning their bib
   and pressing Enter — the race is detected automatically from the
   athlete's roster entry, so you can run this one entry stream for several
   races finishing concurrently (e.g. a combined boys/girls finish chute)
   without switching races. For a bib that doesn't match anyone, or a
   finisher you didn't catch a bib for, use the "Unmatched or no-bib
   finisher" panel to record it against a specific race. Entries appear
   instantly; use ✎ to correct a bib/time/status or 🗑 to remove a mis-entry.
   To reorder a specific race's results or make corrections after the fact,
   switch to the **Finish Order** tab, pick the race, and use ↑/↓.
7. **View results** — the **Results** tab shows live team scores and
   read-only page at `/results/{meet_id}` (linked from the meet header) —
   it needs no login and auto-refreshes every 15 seconds, so announcers or
   spectators can follow along. Each race also gets its own focused, public
   page at `/{meet_id}/{race_slug}` (e.g. `/really_big_invitational_2026/boys_varsity`)
   — handy for texting a single team's results without the whole meet.

## Dashboard passcode

The operator dashboard — everything at `/` and `/meets/...` where meets,
teams, athletes, timing, and races are managed — is gated behind a shared
passcode (`DASHBOARD_PASSCODE`, default `1234`, set via `.env`). Visiting
any dashboard URL without having entered it shows a passcode prompt instead
of the sidebar/content; entering the right passcode sets a cookie (valid 30
days) that unlocks it for that browser.

This is deliberately lightweight — a deterrent against a stray spectator
poking at meet management, not real authentication. The **public results
pages** (`/results/{meet_id}`, `/{meet_id}/{race_slug}`) and the **API
itself** are *not* protected by it: anyone who can reach the API directly
(same LAN, or `BACKEND_PORT`) can still read or write data with no
passcode. Change `DASHBOARD_PASSCODE` in `.env` before race day if the
default matters to you; there's no per-operator login, just the one shared
code.

## Scoring rules

Standard cross country scoring, per race:

- A runner's **place** is their true finish order in the race (1, 2, 3, …),
  including unattached or unmatched (no-bib) runners — this keeps place
  numbers meaningful for scoring even when not every finisher is on a team.
- A team's **score** is the sum of the places of its top *N* runners
  (*N* = the race's configured scoring-athletes count), lowest score wins.
- A team needs at least *N* finishers to receive a score. Teams with fewer
  are shown as **incomplete** and are not ranked.
- The next *D* runners per team (*D* = displacers) don't score, but are used
  to break ties: if two teams have equal scores, the team whose displacer
  finished ahead wins the tie (the classic "6th runner" rule).

This logic lives in [`backend/app/scoring.py`](backend/app/scoring.py).

## API

Full interactive documentation is at `/docs` (Swagger UI) once the backend
is running. Highlights:

| Resource | Endpoints |
|---|---|
| Meets | `GET/POST /api/meets`, `GET/PATCH/DELETE /api/meets/{id}` (`PATCH` with `is_active: true` makes a meet the active one), `GET /api/meets/active` |
| Races | `GET/POST /api/meets/{meet_id}/races`, `GET/PATCH/DELETE /api/races/{id}` (`PATCH` sets/clears `start_time`/`finish_time`) |
| Starts | `GET/POST /api/meets/{meet_id}/starts`, `GET/POST /api/starts` (active meet), `DELETE /api/starts/{id}` |
| Teams | `GET/POST /api/meets/{meet_id}/teams`, `POST /api/meets/{meet_id}/teams/bulk`, `PATCH/DELETE /api/teams/{id}` |
| Athletes | `GET/POST /api/meets/{meet_id}/athletes`, `POST /api/meets/{meet_id}/athletes/bulk`, `PATCH /api/meets/{meet_id}/athletes/bulk` (bulk team and/or race reassignment), `GET/PATCH/DELETE /api/athletes/{id}` |
| Time entry | `GET/POST /api/meets/{meet_id}/finishes`, `GET/POST /api/finishes` (active meet) |
| Finish order | `GET /api/races/{race_id}/finishers`, `PATCH/DELETE /api/finishers/{id}`, `POST /api/races/{race_id}/finishers/reorder` |
| Results | `GET /api/races/{race_id}/results`, `GET /api/meets/{meet_id}/races/{race_slug}/results` (public), `GET /api/meets/{meet_id}/results` (public) |
| Readers | `GET/POST /api/readers`, `GET /api/readers/{label}`, `POST /api/readers/{label}/connect`\|`disconnect`\|`start`\|`stop`, `GET /api/readers/{label}/tags` — see [LLRP readers](#llrp-readers) |
| Tags | `GET /api/tags` (optional `?seconds=`) — all readers' tag reads from the Valkey stream, see [Tag read stream](#tag-read-stream-valkey) |
| Events | `GET /events/{channel}` — live Server-Sent Events for any Valkey pub/sub channel, see [Live events over HTTP](#live-events-over-http-sse) |

`POST /api/meets/{meet_id}/finishes` is deliberately not race-scoped: pass a
`bib` and the race is resolved from that athlete's roster entry, so one
operator can time several concurrently-running races through a single entry
stream without picking a race first. `race_id` in the body is only consulted
as a fallback — for a bib that doesn't match any athlete in the meet, or a
finisher with no bib at all (the finisher is flagged `is_unknown` in either
case). Once recorded, correct or reorder a specific race's results with
`PATCH /api/finishers/{id}` and `POST /api/races/{race_id}/finishers/reorder`.

`POST /api/meets/{meet_id}/starts` records a gun/start event — an optional
`label` and `time` (ISO 8601; defaults to the server's clock if omitted), so
an external starter device or app can fire a single request at gun time with
an empty JSON body (`{}`). A race's own `start_time`/`finish_time` (set via
`PATCH /api/races/{id}`) are independent of the `starts` table — the start
dialog just lists submitted starts (each shown with its time of day and a
live `MM:SS` clock of how long ago it fired) as convenient options when
setting a race's `start_time`, but any race can also be started with
`start_time: "<iso timestamp>"` directly.

`GET`/`POST /api/starts` and `GET`/`POST /api/finishes` are meet-agnostic
counterparts of the `/api/meets/{meet_id}/...` versions above: instead of
taking a meet id in the path, they look up whichever meet is currently
toggled **active** (sidebar toggle, or `PATCH /api/meets/{id}` with
`{"is_active": true}`) and operate on that meet — `GET /api/meets/active`
returns which one that is. They 404 if no meet is currently active. This is
what the [starter module](starter/README.md) uses by default, so it needs
no meet id configured; point it at a specific meet instead via its
`MEET_ID` environment variable if you'd rather bypass the active-meet
toggle entirely.

An external device can POST to either nginx's `/api` path
(`http://<host>/api/...` — the same origin as the dashboard, port 80) or the
**backend** directly (`http://<host>:${BACKEND_PORT:-8000}/api/...`); both
reach the same FastAPI app and behave identically. Avoid going through the
frontend's own port if you ever re-enable it in `docker-compose.yml` — it's
a SvelteKit app, and SvelteKit's CSRF guard rejects any
POST/PUT/PATCH/DELETE whose `Content-Type` looks like an HTML form
(`application/x-www-form-urlencoded`, `multipart/form-data`, or
`text/plain`) unless the `Origin` header matches, which is exactly what
`curl -d` sends by default. Always send an explicit JSON content type:

```bash
curl -X POST http://localhost/api/meets/<meet_id>/starts \
  -H "Content-Type: application/json" \
  -d '{"label": "Gun 1"}'
```

## LLRP readers

Early scaffolding for acquiring finish data from an RFID (LLRP) reader —
currently registering readers and querying their capabilities over a real
LLRP session; a reader isn't wired up to actually produce finish records
yet. A reader is hardware, not meet data, so it's registered once and
reused across meets (not scoped to a meet id like everything else in the
API). The LLRP session itself is handled by
[pyllrp](https://github.com/esitarski/pyllrp) (`backend/app/llrp.py`).

- `POST /api/readers` registers one — pass `ip_address` and, optionally,
  `label`; if `label` is omitted it's derived from the IP
  (`192.168.8.21` → `192_168_8_21`). Labels must be unique.
- `GET /api/readers` / `GET /api/readers/{label}` list/fetch registered
  readers, including `manufacturer`, `product`, and `num_antennas` as last
  reported by the reader (all `null` until a successful connect).
- `POST /api/readers/{label}/connect` opens a real LLRP session against the
  reader's IP on the standard LLRP port (5084) — TCP connect, the
  `READER_EVENT_NOTIFICATION` handshake, then two requests. First,
  `GET_READER_CAPABILITIES`, storing `num_antennas` (the reader's total
  antenna *port* count — a hardware capability, present regardless of
  what's actually plugged in) and manufacturer/model as the numeric codes
  LLRP itself uses (an IANA vendor ID and a vendor-assigned model number —
  not free-text), with known vendor IDs like Impinj's resolved to a name.
  Second, `GET_READER_CONFIG` requesting `AntennaProperties`, storing
  `connected_antennas` — the antenna IDs that specific parameter reports as
  actually having an antenna connected right now, which can be fewer than
  `num_antennas` (e.g. a 4-port reader with only one antenna cabled up).
  If a reader doesn't support that second query, `connected_antennas` stays
  `null` (not an empty list — "unknown" and "confirmed none connected" are
  different things) without failing the connect. The session is then
  closed; nothing is kept open.

  Once the LLRP connect succeeds, it also makes one best-effort, no-retry
  attempt at the reader's own web admin page — Impinj's `cgi-bin/index.cgi`
  (factory-default `root`/`impinj` credentials) or Zebra/Motorola's
  `help/about.psp`, picked by the manufacturer LLRP just resolved — to
  replace the numeric manufacturer/model with the human-readable strings
  those pages report (e.g. `product` becomes `"Speedway R420"` instead of
  `"2001714"`). Any failure there (blocked port, reader doesn't expose that
  page, unexpected page contents) is silently ignored and the numeric LLRP
  values are kept — this step can only improve on what LLRP already gave
  you, never fail the connect. See `backend/app/reader_info.py`.

  A failure in the LLRP step itself (wrong IP, powered-off reader, reader
  already claimed by another client) sets `status` to `disconnected` and
  returns the reader's own error text with a 502.
- `POST /api/readers/{label}/start` starts continuously reading tags: opens
  a persistent LLRP connection (if one isn't already open), adds and
  enables an inventory ROSpec configured to run until stopped, and starts a
  background thread that receives `RO_ACCESS_REPORT` messages as they
  arrive and buffers the most recent 500 reads in memory. No-op if already
  reading. `POST /api/readers/{label}/stop` stops the ROSpec and listener
  thread but leaves the connection itself open, so a later `.../start` is
  fast — no-op if not currently reading.
- `GET /api/readers/{label}/tags` returns `{"reading": bool, "tags": [...]}`
  — the buffered recent reads (oldest first), each with `tag` (the EPC,
  hex-decoded — only reads whose hex digits are all `0`-`9` are kept, per
  this deployment's tag-provisioning convention), `antenna_id`,
  `peak_rssi`, and `time`. Meant to be polled by the UI (the Readers page
  does this every 1.5s while a reader's tag panel is open).
- `POST /api/readers/{label}/disconnect` stops any active reading session
  and fully closes the connection, then sets `status` to `disconnected`.

  This tag-streaming session is in-memory, per-process state
  (`backend/app/llrp_session.py`) — it does not survive a backend restart,
  and only works with a single backend process (this app runs uvicorn
  without `--workers`, so that's fine here, but it's worth knowing if that
  ever changes). Turning these raw tag reads into finish records (matching
  a tag to a bib/athlete) is still follow-up work — right now this only
  gets tag IDs into a buffer the UI can watch.

### Tag read stream (Valkey)

Every tag read is `XADD`ed to a [Valkey](https://valkey.io/) stream named
`livestream` (`backend/app/tag_stream.py`) — a durable, external record of
raw reads, independent of the in-memory buffer above and of any particular
backend process's lifetime — and also `PUBLISH`ed (as JSON) to the
`tag_read` pub/sub channel, for a consumer that wants to react to reads as
they happen instead of polling the stream:

```bash
valkey-cli -h localhost SUBSCRIBE tag_read
```

Both carry the same fields per read:

| Field | Description |
|---|---|
| `event_type` | Always `tag_read` |
| `tag` | The EPC, hex-decoded |
| `antenna` | Antenna ID the tag was read on |
| `rssi` | Signal strength reported for the read |
| `time` | ISO 8601 wall-clock time of the read |
| `timestamp` | The same moment as `time`, as Unix epoch seconds |
| `label` | The reader's label |
| `reader_id` | The reader's serial number, if known (blank otherwise — see [LLRP readers](#llrp-readers)'s note on the vendor web page lookup) |

`livestream` isn't tag-reads-only, despite the name of this section — the
[starter module](starter/README.md) mirrors each start onto the same
stream (`event_type: "start"`, with `label`/`meet_id`/`time`/`timestamp`
fields but none of the tag-specific ones above) and publishes it to its own
`start` channel, so a consumer scanning the whole stream sees every live
event this app produces, told apart by `event_type`.

This is meant for diagnostics and for other tools/processes to consume
independently of this app — `valkey` is published on the host specifically
for that (`VALKEY_PORT`, default 6379):

```bash
valkey-cli -h localhost XRANGE livestream - +      # everything, oldest first
valkey-cli -h localhost XREAD COUNT 10 BLOCK 0 STREAMS livestream '$'   # follow live
```

`GET /api/tags` exposes the same stream over HTTP — `XRANGE`, scoped to a
recent time window rather than the whole stream, spanning every reader (not
one at a time like `GET /api/readers/{label}/tags`). Defaults to the last 5
seconds; pass `?seconds=` to widen or narrow the window, e.g.
`GET /api/tags?seconds=30`. This is a snapshot/backfill API — good for "what
happened in the last N seconds" from a script or curl — rather than
something to poll for a live view; see below for that.

Both the `XADD` and the `PUBLISH` are best-effort and independent of each
other: if Valkey is unreachable, or only one of the two calls fails, tag
reading itself is unaffected (each failure is logged as a warning on its
own) — but note this means both `GET /api/tags` and the live events below
depend on Valkey being up, unlike the per-reader in-memory buffer
(`GET /api/readers/{label}/tags`), which doesn't.

### Live events over HTTP (SSE)

`GET /events/<channel>` streams a Valkey pub/sub channel to any HTTP client
as [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
— e.g. `/events/tag_read` streams the same messages the `tag_read` channel
above carries, live, with no polling involved. It's served by its own
container (`events/server.go`), a small Go binary built without a web
framework (just `net/http` + `go-redis`) to stay as small as possible — the
image is a `scratch`-based binary under 20MB and idles at a few MB of RAM.
It knows nothing about tag reads specifically; `<channel>` can be any
Valkey pub/sub channel, including ones this app doesn't otherwise know
about.

```bash
curl -N http://localhost/events/tag_read
```

This is what the Readers page itself subscribes to (via the browser's
native `EventSource`, no polling and no client library) for its "Tag reads"
list and for lighting up each reader's antenna badges live — an antenna
badge lights when that reader+antenna produced a read in roughly the last
second; with **Antenna Test Mode** toggled on, a badge stays lit once
triggered — across every reader — until the toggle is turned back off, so
an operator can walk a tag past each antenna and check them all afterward
instead of catching each one lighting up in real time. `EventSource`
reconnects on its own if the connection drops (the page shows a "Live tag
stream disconnected — reconnecting…" notice meanwhile); each event's
`antenna`/`rssi`/`timestamp` arrive as strings (`XADD` requires string
field values) and are parsed client-side, unlike `/api/tags`'s already-typed
JSON response.

Each line is either `data: <the published message>` or a `: comment` —
either an initial `: connected` or a `: keep-alive` sent every 15s while
nothing's been published, so the connection doesn't look dead to nginx or
the browser. nginx proxies `/events/` to it with buffering disabled and a
long read timeout (`nginx/default.conf`), both required for a stream that's
meant to stay open indefinitely. Not published directly to the host — reach
it through nginx, same as the frontend.

## Local development (without Docker)

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_HOST=localhost   # point at a local/dockerized Postgres
alembic upgrade head
python -m app.seed               # optional demo data
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
INTERNAL_API_URL=http://localhost:8000 npm run dev
```

## Database migrations

Migrations are managed with Alembic (`backend/alembic/`). To create a new
migration after changing `backend/app/models.py`:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
```

Review the generated file before committing — autogenerate is a helpful
starting point, not a guarantee. Migrations run automatically on container
startup (see `backend/docker-entrypoint.sh`).

## Configuration reference

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `openxc` | Database credentials |
| `POSTGRES_PORT` | `5432` | Host port for Postgres (rarely needs changing) |
| `BACKEND_PORT` | `8000` | Host port for the API (direct access — see [Architecture](#architecture)) |
| `CORS_ORIGINS` | `*` | Allowed origins if calling the API directly |
| `SEED_DEMO_DATA` | `true` | Seed a demo meet on first boot |
| `HTTP_PORT` | `80` | Host port for nginx — the app's main entry point |
| `DASHBOARD_PASSCODE` | `1234` | Passcode required to unlock the operator dashboard — see [Dashboard passcode](#dashboard-passcode) |
| `VALKEY_PORT` | `6379` | Host port for Valkey — see [Tag read stream](#tag-read-stream-valkey) |

## Running on a Raspberry Pi / ARM64

No changes needed — every image used (`python:3.12-slim`, `python:3.12-alpine`,
`node:20-alpine`, `postgres:16-alpine`, `valkey/valkey:8-alpine`,
`nginx:1.27-alpine`) publishes multi-arch builds, and `docker compose up
--build` will build native ARM64 images on-device. Expect the first build to
take a few minutes on a Pi; subsequent starts are fast.

## Project website

`docs/index.html` is a static marketing/landing page for the project — not
part of the app itself, and not built or served by Docker Compose. It's a
single self-contained file (inline CSS, no build step, no external
dependencies) meant for GitHub Pages: in the repo's Settings → Pages, set
**Source** to `Deploy from a branch`, branch `main`, folder `/docs`. It'll
publish at `https://<org-or-user>.github.io/<repo>/`. Edit it directly and
push — no rebuild step.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
