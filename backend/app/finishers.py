from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models

_VACATED_PLACE = -1


def next_place(db: Session, race_id: str) -> int:
    max_place = db.query(func.max(models.Finisher.place)).filter(models.Finisher.race_id == race_id).scalar() or 0
    return max_place + 1


def close_place_gap(db: Session, race_id: str, removed_place: int) -> None:
    """Shift every finisher after `removed_place` down by one, closing the gap
    left by removing or moving a finisher out of this race.

    Shifted through a negative holding value first: the unit of work doesn't
    guarantee these UPDATEs execute in place order, and decrementing in place
    (e.g. 13 -> 12) can transiently collide with a neighbor that hasn't moved
    yet under the (race_id, place) unique constraint.
    """
    to_shift = (
        db.query(models.Finisher)
        .filter(models.Finisher.race_id == race_id, models.Finisher.place > removed_place)
        .order_by(models.Finisher.place.asc())
        .all()
    )
    if not to_shift:
        return
    for f in to_shift:
        f.place = -f.place
    db.flush()
    for f in to_shift:
        f.place = -f.place - 1
    db.flush()


def resolve_athlete_by_bib(db: Session, meet_id: str, bib: str | None) -> models.Athlete | None:
    if not bib:
        return None
    return (
        db.query(models.Athlete)
        .filter(models.Athlete.meet_id == meet_id, models.Athlete.bib == bib)
        .first()
    )


def reassign_athlete_finishers(db: Session, athlete_id: str, new_race_id: str | None) -> None:
    """Keep recorded finishes in sync with an athlete's current race.

    Called when an athlete's race assignment changes. Any finish already
    recorded for this athlete is moved into their new race (appended to the
    end of its current finish order), so results stay correct without the
    operator having to re-enter anything. Finishers without a resolvable
    athlete (no-bib / unmatched-bib entries) are untouched since there's no
    athlete record to derive a race from — those keep whatever race they
    were manually recorded in. If the athlete is unassigned (no race), any
    existing finishes are left where they are rather than orphaned.
    """
    if not new_race_id:
        return

    finishers = db.query(models.Finisher).filter(models.Finisher.athlete_id == athlete_id).all()
    for finisher in finishers:
        if finisher.race_id == new_race_id:
            continue
        old_race_id = finisher.race_id
        old_place = finisher.place

        # Vacate this finisher's old slot before shifting others into it —
        # otherwise the shift-down collides with this still-present row.
        finisher.place = _VACATED_PLACE
        db.flush()

        close_place_gap(db, old_race_id, old_place)

        finisher.race_id = new_race_id
        finisher.place = next_place(db, new_race_id)
        db.flush()
