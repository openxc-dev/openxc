"""Automatically records a finish when an RFID tag is read while its race
is in progress. Called from llrp_session.py's background listener thread
for every digit-only tag read (the EPC's digits are the athlete's bib,
same convention the rest of the app uses) — not a request thread, so this
opens its own short-lived DB session rather than depending on FastAPI's
per-request one.

Duplicate reads (the same tag is reported many times per second while a
runner passes the antenna) are dropped via an in-memory set of
(race_id, tag_id) pairs already turned into a finish, kept for the
lifetime of this process. A DB check right before inserting is a second,
authoritative guard against double-recording the same athlete in a race
(e.g. an operator having already entered it by hand).
"""

import logging
import threading
from datetime import datetime, timezone

from app import models
from app.database import SessionLocal
from app.finishers import next_place

log = logging.getLogger(__name__)

_seen_lock = threading.Lock()
_seen: set[tuple[str, str]] = set()  # (race_id, tag_id) already turned into a finish


def record_finish_from_tag(tag_id: str, read_time: datetime | None) -> None:
    db = SessionLocal()
    try:
        meet = db.query(models.Meet).filter(models.Meet.is_active.is_(True)).first()
        if not meet:
            return

        athlete = (
            db.query(models.Athlete)
            .filter(models.Athlete.meet_id == meet.id, models.Athlete.bib == tag_id)
            .first()
        )
        if not athlete or not athlete.race_id:
            return

        race = db.get(models.Race, athlete.race_id)
        if not race or race.start_time is None or race.finish_time is not None:
            return  # this athlete's race isn't currently in progress

        key = (race.id, tag_id)
        with _seen_lock:
            if key in _seen:
                return
            _seen.add(key)

        existing = (
            db.query(models.Finisher)
            .filter(models.Finisher.race_id == race.id, models.Finisher.athlete_id == athlete.id)
            .first()
        )
        if existing:
            return

        event_time = read_time or datetime.now(timezone.utc)
        time_seconds = max(0.0, (event_time - race.start_time).total_seconds())

        finisher = models.Finisher(
            race_id=race.id,
            athlete_id=athlete.id,
            bib=athlete.bib,
            place=next_place(db, race.id),
            time_seconds=time_seconds,
            status=models.FinishStatus.FINISHED.value,
            is_unknown=False,
        )
        db.add(finisher)
        db.commit()
        log.info(
            "Auto-recorded finish for bib %s in race %r (%.2fs)", tag_id, race.name, time_seconds
        )
    except Exception:
        log.exception("Failed to auto-record finish for tag %s", tag_id)
        db.rollback()
    finally:
        db.close()
