# Starter module

Watches a host-written file for starting-gun trigger events and posts each
one to the OpenXC API with the label `Starting Gun`, so it shows up as a
pickable option in the app's Start dialog on the Races tab. By default it
posts to `POST /api/starts`, which resolves to whichever meet is currently
marked **active** in the dashboard sidebar — set `MEET_ID` to always post
to one specific meet instead (`POST /api/meets/{meet_id}/starts`).

This is an optional, hardware-integration piece — most setups won't need
it and can ignore this directory entirely.

## How it works

1. Something on the host — a GPIO handler, a button daemon, whatever's
   wired to the actual starting gun — **appends an 8-byte binary integer**
   to a file (default `/var/run/trigger_events`) every time the gun fires.
   The file is therefore an ever-growing log of fixed-size records, oldest
   first; each integer is a `CLOCK_MONOTONIC` reading (in nanoseconds by
   default) taken at the moment of that trigger.
2. This container watches that file for growth, two ways at once for
   redundancy: `inotify` for near-instant detection, plus a periodic poll
   as a fallback. At startup it notes the file's current size and reports
   nothing already in it — only records appended from then on. Whichever
   watcher notices growth first reads and posts the new record(s); the
   other is a no-op until the file grows again, so nothing is double-posted.
3. For each new record, it compares the value against its own current
   `CLOCK_MONOTONIC` and `CLOCK_REALTIME` readings to work out the elapsed
   time since that trigger, and derives a wall-clock timestamp from that —
   then POSTs it. If several records were appended between checks (e.g. the
   poll interval was slow to catch up), each is posted in order.
4. Alongside that POST — the authoritative delivery — each start is also
   mirrored into Valkey: `XADD`ed onto the shared `livestream` stream (the
   same one finish-line tag reads go into; see the main `README.md`'s "Tag
   read stream" section) and `PUBLISH`ed to the `start` channel for live
   subscribers, e.g. `GET /events/start` (see the main README's "Live
   events over HTTP"). Both are best-effort: if Valkey is unreachable, the
   failure is logged and otherwise ignored — it never blocks or fails the
   actual start.

The **containing directory** (`/var/run` by default) is bind-mounted, not
the trigger file itself — this matters, see below.

## Why the directory is mounted, not the file

A bind mount of a single file pins to that file's inode at mount time. If
the host writer appends in place — the normal case here, and how the file
is expected to be written — a single-file mount would actually keep working
fine, since it's still the same inode just growing. But if the file is ever
*recreated* instead (log rotation, a restart that truncates and starts
over, replacing it via the standard temp-file-plus-`os.rename()` pattern),
a single-file mount would silently keep seeing the original, now-stale
inode forever, and both inotify and the poll loop would stop seeing new
records. Watching the containing directory and filtering events by
filename (see `inotifyLoop` in `starter.go`) survives that case too. One
consequence: because the mount source is a directory that already exists,
you don't need to pre-create the trigger file before starting the
container the way you would with a single-file mount. Separately, if the
file's size is ever observed to *shrink* (a recreate/truncate happened),
`starter.go` logs a warning and resumes from the new end rather than
re-reading or erroring — it deliberately doesn't try to guess which old
records, if any, were already reported before the file was replaced.

## Format assumptions — check these against your actual trigger writer

Each 8-byte record is interpreted as an unsigned 64-bit integer,
**little-endian**, in **nanoseconds**, by default. All three are adjustable
via environment variables (`VALUE_BYTE_ORDER`, `VALUE_UNIT`) without
touching code — see the table below. If events aren't showing up, or show
up with an obviously wrong time, this is the first thing to check: read a
real trigger file with `xxd /var/run/trigger_events` and confirm the byte
order and unit match what your host-side writer actually produces, and
that it's appending 8-byte records rather than overwriting.

## Important: this only works on a shared kernel

Converting a monotonic reading into a wall-clock time by diffing it against
this container's own clocks is only valid if this container observes the
**same** `CLOCK_MONOTONIC` counter as whatever wrote the file. That's true
on a native Linux host (including a Raspberry Pi) or bare Docker Engine,
because containers share the host kernel. It is **not** true through
Docker Desktop on macOS or Windows, which runs containers inside a
lightweight Linux VM with its own, unrelated monotonic clock — if the
trigger-writer runs on the Mac/Windows host itself (outside that VM), the
computed times will be wrong. Run this on the same Linux box that's wired
to the hardware.

## Setup

In the dashboard sidebar, flip the toggle on the meet you want tonight's
starting gun to post to — that's the "active" meet `/api/starts` resolves
to. Nothing else to configure by default.

Then bring it up — it's excluded from a plain `docker compose up` via a
Compose profile, since it needs a host trigger file to do anything useful:

```bash
docker compose --profile starter up -d --build starter
```

If you'd rather this always post to one specific meet regardless of the
active-meet toggle, set it in your `.env` instead:

```bash
STARTER_MEET_ID=really_big_invitational_2026
```

Watch its logs to confirm it's watching correctly and picking up events:

```bash
docker compose logs -f starter
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `MEET_ID` | *(unset)* | Meet id/slug to always post starts to. Set via `STARTER_MEET_ID` in `.env`. Leave unset to post to `/api/starts` — whichever meet is toggled "active" in the sidebar. |
| `TRIGGER_FILE` | `/host-var-run/trigger_events` in Docker (`/var/run/trigger_events` if run outside Docker) | Path to the trigger file, from this process's point of view. |
| `API_BASE_URL` | `http://backend:8000` | Base URL of the API. The default talks to the `backend` container directly over the internal Docker network. |
| `LABEL` | `Starting Gun` | Label attached to each posted start. |
| `VALUE_BYTE_ORDER` | `little` | `little` or `big` — byte order of the 8-byte integer. |
| `VALUE_UNIT` | `ns` | `ns`, `us`, `ms`, or `s` — unit of the monotonic reading. |
| `POLL_INTERVAL_SECONDS` | `5` | How often the fallback poll re-checks the file. |
| `MAX_REASONABLE_DELAY_SECONDS` | `3600` | A computed event time further than this from "now" is logged and dropped rather than posted — guards against posting garbage from an empty/misconfigured file. |
| `VALKEY_HOST` / `VALKEY_PORT` | `valkey` / `6379` | Where to mirror each start (`XADD` to `livestream`, `PUBLISH` to `start`) — see step 4 above. A connection failure here is logged and otherwise ignored. |

## Testing without real hardware

Append a record by hand to simulate a trigger firing right now (matches the
default little-endian/nanoseconds format — note the `ab` append mode, since
that's how the real writer is expected to behave). Run this on the host —
not inside the container — so it observes the same monotonic clock, per the
shared-kernel caveat above:

```bash
python3 -c "
import time
with open('/var/run/trigger_events', 'ab') as f:
    f.write(time.clock_gettime_ns(time.CLOCK_MONOTONIC).to_bytes(8, 'little'))
"
```

`docker compose logs -f starter` should show it detected and posted within
a couple of seconds, and the new start should appear in the Start dialog's
list on the Races tab. Run the same command again (e.g. after waiting a bit)
to simulate a second, independent trigger — it appends a second record, and
only that new one gets reported, not the first one again.

To exercise the file-recreation path (temp file + rename) that the
directory-mount approach above is specifically for:

```bash
python3 -c "
import os, time
tmp = '/var/run/.trigger_events.tmp'
with open(tmp, 'wb') as f:
    f.write(time.clock_gettime_ns(time.CLOCK_MONOTONIC).to_bytes(8, 'little'))
os.rename(tmp, '/var/run/trigger_events')
"
```

That one replaces the file outright (one record, freshly created) rather
than appending — logs should show a "shrank ... resuming from its current
end" warning followed by that record being picked up.
