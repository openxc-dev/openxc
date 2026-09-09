#!/usr/bin/env python3
"""Watches a host-written trigger file for starting-gun events and posts
each one to the OpenXC starts API. If MEET_ID is set, posts to
POST /api/meets/{meet_id}/starts; otherwise posts to POST /api/starts,
which resolves to whichever meet is currently marked "active" in the
dashboard — the simpler option day-to-day, since it needs no per-meet
reconfiguration here.

The trigger file (TRIGGER_FILE, default /var/run/trigger_events) is written
by host-side/hardware code whenever the starting gun fires: each firing
*appends* an 8-byte binary integer to the file — a CLOCK_MONOTONIC reading,
in nanoseconds by default, taken at the moment of the trigger. So the file
only ever grows, one 8-byte record per event, oldest first. See README.md
in this directory for the full format assumptions (byte order, unit) and
why a monotonic reading only converts correctly to wall-clock time when
this container shares a kernel with whatever wrote the file (true on a
native Linux host or a Raspberry Pi; NOT true through Docker Desktop's VM).

At startup, this process notes the file's current size and reports nothing
already present — only records appended *after* it started watching. From
then on, every time the file grows by 8 bytes it reads and reports that
new trailing record (not the file's first record, which is what a naive
"always read the first 8 bytes" implementation would keep re-reading).

Watched two ways at once, per the operator's request for redundancy:
  - inotify, for near-instant detection (a small ctypes binding below —
    deliberately stdlib-only, no third-party dependency for this).
  - a periodic poll, in case inotify doesn't fire (bind-mounted host files
    don't always propagate filesystem events reliably into a container).

Both feed into the same offset-tracking check, so whichever notices growth
first is the one that reads and posts the new record(s); the other is a
no-op until the file grows again.
"""

import ctypes
import ctypes.util
import json
import logging
import os
import select
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# --- Configuration ---------------------------------------------------------

TRIGGER_FILE = os.environ.get("TRIGGER_FILE", "/var/run/trigger_events")
API_BASE_URL = os.environ.get("API_BASE_URL", "http://backend:8000").rstrip("/")
MEET_ID = os.environ.get("MEET_ID", "").strip()
LABEL = os.environ.get("LABEL", "Starting Gun")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "5"))

# How the 8 bytes in the trigger file are interpreted. Both are adjustable
# without touching code, in case the actual host writer differs from the
# assumed "little-endian, nanoseconds" convention.
VALUE_BYTE_ORDER = os.environ.get("VALUE_BYTE_ORDER", "little")  # "little" or "big"
VALUE_UNIT = os.environ.get("VALUE_UNIT", "ns")  # "ns", "us", "ms", or "s"
_UNIT_TO_NS = {"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000}

# Guards against posting nonsense if the file is empty/zeroed/misconfigured:
# a resulting event time further than this from "now" is dropped, not posted.
MAX_REASONABLE_DELAY_SECONDS = float(os.environ.get("MAX_REASONABLE_DELAY_SECONDS", "3600"))

# HTTP retry policy for the POST itself (transient backend hiccups).
POST_RETRIES = 3
POST_RETRY_DELAY_SECONDS = 2

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("starter")


# --- Minimal inotify binding (stdlib-only, via ctypes) ----------------------
#
# We watch the *containing directory*, not the trigger file itself, and
# filter events by filename. Watching the file directly binds the watch to
# its current inode; if the writer replaces the file via the standard
# atomic-write pattern (write a temp file, then os.rename() over the
# target — the safe way to avoid a reader seeing a torn/partial write),
# that inode is swapped out from under us and a file-level watch silently
# stops seeing anything. Watching the directory for CREATE/MOVED_TO/
# CLOSE_WRITE events naming our file catches both in-place writes and
# atomic replacements.

_IN_MODIFY = 0x00000002
_IN_ATTRIB = 0x00000004
_IN_CLOSE_WRITE = 0x00000008
_IN_CREATE = 0x00000100
_IN_MOVED_TO = 0x00000080
_WATCH_MASK = _IN_MODIFY | _IN_ATTRIB | _IN_CLOSE_WRITE | _IN_CREATE | _IN_MOVED_TO

_EVENT_HEADER = struct.Struct("iIII")  # wd, mask, cookie, name_len


class Inotify:
    """Tiny ctypes wrapper around the Linux inotify syscalls — deliberately
    minimal (just what's used here) to avoid a third-party dependency."""

    def __init__(self):
        libc_path = ctypes.util.find_library("c")
        self._libc = ctypes.CDLL(libc_path, use_errno=True)
        self.fd = self._libc.inotify_init1(0)
        if self.fd == -1:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")

    def watch(self, path):
        wd = self._libc.inotify_add_watch(self.fd, path.encode(), _WATCH_MASK)
        if wd == -1:
            raise OSError(ctypes.get_errno(), f"inotify_add_watch failed for {path}")
        return wd

    def read_events(self, timeout_seconds):
        """Blocks up to timeout_seconds for events; returns a list of
        (wd, mask, cookie, name) tuples, or [] on timeout. `name` is the
        filename the event pertains to (empty string for watches on a
        single file rather than a directory)."""
        ready, _, _ = select.select([self.fd], [], [], timeout_seconds)
        if not ready:
            return []
        data = os.read(self.fd, 64 * 1024)
        events = []
        pos = 0
        while pos < len(data):
            wd, mask, cookie, name_len = _EVENT_HEADER.unpack_from(data, pos)
            pos += _EVENT_HEADER.size
            raw_name = data[pos : pos + name_len]
            pos += name_len
            name = raw_name.split(b"\0", 1)[0].decode(errors="replace")
            events.append((wd, mask, cookie, name))
        return events

    def close(self):
        os.close(self.fd)


# --- Trigger file handling ---------------------------------------------------

def _file_size(path):
    """Current size of path in bytes, or None if it doesn't exist yet —
    treated as "empty" rather than an error, since the writer may not have
    created it yet when this process starts."""
    try:
        return os.path.getsize(path)
    except FileNotFoundError:
        return None


def monotonic_ns_to_wallclock(trigger_monotonic_ns):
    """Converts a CLOCK_MONOTONIC nanosecond reading into a wall-clock
    datetime by diffing it against *this process's own* current monotonic
    and real-time clocks. CLOCK_MONOTONIC's zero point is arbitrary and not
    portable across machines/processes, so we never treat the raw value as
    an absolute time — only the elapsed delta is meaningful, which is valid
    as long as this container observes the same monotonic clock as whatever
    wrote the file (true on a native Linux host / Raspberry Pi; not true
    through Docker Desktop's VM — see README.md)."""
    now_monotonic_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    now_real_ns = time.clock_gettime_ns(time.CLOCK_REALTIME)
    elapsed_ns = now_monotonic_ns - trigger_monotonic_ns
    event_real_ns = now_real_ns - elapsed_ns
    return datetime.fromtimestamp(event_real_ns / 1e9, tz=timezone.utc), elapsed_ns


def post_start(event_time):
    url = f"{API_BASE_URL}/api/meets/{MEET_ID}/starts" if MEET_ID else f"{API_BASE_URL}/api/starts"
    payload = json.dumps({"label": LABEL, "time": event_time.isoformat()}).encode()

    for attempt in range(1, POST_RETRIES + 1):
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info("Posted start %s -> HTTP %s", event_time.isoformat(), resp.status)
                return
        except urllib.error.HTTPError as e:
            log.error("POST %s failed: HTTP %s %s", url, e.code, e.read().decode(errors="replace"))
            return  # a 4xx/5xx from the API won't be fixed by retrying the same body
        except urllib.error.URLError as e:
            log.warning(
                "POST %s failed (attempt %d/%d): %s", url, attempt, POST_RETRIES, e.reason
            )
            if attempt < POST_RETRIES:
                time.sleep(POST_RETRY_DELAY_SECONDS)

    log.error("Giving up posting start %s after %d attempts", event_time.isoformat(), POST_RETRIES)


# --- Append-tracking change detection ---------------------------------------

class TriggerWatcher:
    """Tracks how much of the (append-only) trigger file has been consumed
    so far, as a byte offset shared between the inotify thread and the poll
    loop — whichever of them notices growth first reads and posts the new
    record(s); the other is a no-op until the file grows again. Starts at
    the file's current size, so restarting this container doesn't re-post
    records that were already there before it started watching."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.offset = _file_size(path) or 0
        if self.offset:
            log.info(
                "%s already has %d bytes (%d prior record(s)) — starting from "
                "the end; only records appended from now on will be reported.",
                path, self.offset, self.offset // 8,
            )

    def check(self, source):
        with self.lock:
            size = _file_size(self.path)
            if size is None:
                return
            if size < self.offset:
                log.warning(
                    "%s shrank from %d to %d bytes — it was likely recreated as a "
                    "new file; treating all %d byte(s) currently in it as unseen.",
                    self.path, self.offset, size, size,
                )
                self.offset = 0
            count = (size - self.offset) // 8
            if count == 0:
                return
            try:
                with open(self.path, "rb") as f:
                    f.seek(self.offset)
                    raw = f.read(count * 8)
            except FileNotFoundError:
                return
            except IsADirectoryError:
                log.error("%s is a directory, not a file — check TRIGGER_FILE.", self.path)
                return
            # Only consume whole 8-byte records — a short read means we
            # raced an in-progress append; the remainder is picked up next
            # time the file grows past a full record boundary.
            count = len(raw) // 8
            if count == 0:
                return
            self.offset += count * 8

        log.info("%s grew by %d record(s), detected via %s", self.path, count, source)
        fmt = "<Q" if VALUE_BYTE_ORDER == "little" else ">Q"
        for i in range(count):
            raw_value = struct.unpack_from(fmt, raw, i * 8)[0]
            self._report(raw_value * _UNIT_TO_NS[VALUE_UNIT])

    def _report(self, trigger_monotonic_ns):
        event_time, elapsed_ns = monotonic_ns_to_wallclock(trigger_monotonic_ns)
        elapsed_seconds = elapsed_ns / 1e9
        if abs(elapsed_seconds) > MAX_REASONABLE_DELAY_SECONDS:
            log.warning(
                "Ignoring trigger record monotonic_ns=%d: computed event time %s is "
                "%.0fs from now, past MAX_REASONABLE_DELAY_SECONDS=%.0f — likely a "
                "misread or misconfigured trigger file, not a real event.",
                trigger_monotonic_ns, event_time.isoformat(), elapsed_seconds,
                MAX_REASONABLE_DELAY_SECONDS,
            )
            return
        post_start(event_time)


def inotify_loop(watcher, stop_event):
    target_dir = os.path.dirname(watcher.path) or "."
    target_name = os.path.basename(watcher.path)

    while not stop_event.is_set():
        try:
            inotify = Inotify()
            inotify.watch(target_dir)
            log.info("inotify watching %s for changes to %s", target_dir, target_name)
            try:
                while not stop_event.is_set():
                    events = inotify.read_events(timeout_seconds=2)
                    if any(name == target_name for _, _, _, name in events):
                        watcher.check("inotify")
            finally:
                inotify.close()
        except FileNotFoundError:
            log.warning("%s does not exist yet; retrying inotify watch in 5s", target_dir)
            stop_event.wait(5)
        except OSError as e:
            log.error("inotify error (%s); restarting watch in 5s", e)
            stop_event.wait(5)


def poll_loop(watcher, stop_event):
    while not stop_event.is_set():
        watcher.check("poll")
        stop_event.wait(POLL_INTERVAL_SECONDS)


def main():
    target = f"meet {MEET_ID}" if MEET_ID else "the active meet"
    log.info(
        "Watching %s (unit=%s, byte_order=%s), posting to %s as label=%r for %s "
        "(poll every %.0fs as an inotify fallback)",
        TRIGGER_FILE, VALUE_UNIT, VALUE_BYTE_ORDER, API_BASE_URL, LABEL, target,
        POLL_INTERVAL_SECONDS,
    )
    if not MEET_ID:
        log.info(
            "MEET_ID is not set, so posts go to /api/starts (the active meet). "
            "Mark a meet active in the dashboard before the gun fires, or set "
            "MEET_ID to always post to one specific meet."
        )

    watcher = TriggerWatcher(TRIGGER_FILE)
    stop_event = threading.Event()

    inotify_thread = threading.Thread(target=inotify_loop, args=(watcher, stop_event), daemon=True)
    inotify_thread.start()

    try:
        poll_loop(watcher, stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
