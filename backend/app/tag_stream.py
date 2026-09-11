"""Writes each tag read to a Valkey stream (`livestream`) for diagnostics and
consumption outside this app — separate from the in-memory buffer in
llrp_session.py, which only feeds this app's own UI and doesn't survive a
backend restart. Best-effort: a Valkey outage never blocks or breaks tag
reading itself, it just means that particular read doesn't show up in the
stream (logged as a warning).
"""

import logging
import time

import redis

from app.config import settings

log = logging.getLogger(__name__)

STREAM_KEY = "livestream"
EVENT_TYPE = "tag_read"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = redis.Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)
    return _client


def record_tag_read(*, antenna, rssi, timestamp, tag, time, label, reader_id):
    """XADDs one tag read to the shared stream. Stream field values must be
    strings/bytes/numbers — None is written as an empty string rather than
    omitting the field, so every entry has a consistent set of fields."""
    fields = {
        "antenna": "" if antenna is None else str(antenna),
        "rssi": "" if rssi is None else str(rssi),
        "timestamp": "" if timestamp is None else str(timestamp),
        "tag": tag or "",
        "time": time or "",
        "event_type": EVENT_TYPE,
        "label": label or "",
        "reader_id": reader_id or "",
    }
    try:
        _get_client().xadd(STREAM_KEY, fields)
    except redis.RedisError as e:
        log.warning("Could not write tag read to Valkey stream %r: %s", STREAM_KEY, e)


def _parse_entry(entry_id: str, fields: dict) -> dict:
    """Converts one raw stream entry (string values, per XADD's requirement)
    back into typed values for the API response."""

    def _int_or_none(v):
        return int(v) if v else None

    def _float_or_none(v):
        return float(v) if v else None

    return {
        "id": entry_id,
        "event_type": fields.get("event_type", ""),
        "tag": fields.get("tag", ""),
        "antenna": _int_or_none(fields.get("antenna")),
        "rssi": _int_or_none(fields.get("rssi")),
        "timestamp": _float_or_none(fields.get("timestamp")),
        "time": fields.get("time") or None,
        "label": fields.get("label", ""),
        "reader_id": fields.get("reader_id", ""),
    }


def read_recent(seconds: float = 5.0) -> list[dict]:
    """XRANGEs the stream for entries from the last `seconds` seconds up to
    now, oldest first. Stream IDs are `<millis>-<seq>`, so a plain
    millisecond value works as an inclusive lower bound (Valkey treats it as
    `<millis>-0`). Returns [] (logged as a warning) if Valkey is unreachable,
    rather than raising — this is a read path the UI polls frequently, and a
    transient Valkey hiccup shouldn't surface as a hard API error."""
    now_ms = int(time.time() * 1000)
    start_ms = max(0, now_ms - int(seconds * 1000))
    try:
        entries = _get_client().xrange(STREAM_KEY, min=str(start_ms), max="+")
    except redis.RedisError as e:
        log.warning("Could not read from Valkey stream %r: %s", STREAM_KEY, e)
        return []
    return [_parse_entry(entry_id, fields) for entry_id, fields in entries]
