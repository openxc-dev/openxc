from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.finishers import next_place, resolve_athlete_by_bib
from app.routers.meets import get_active_meet_or_404

router = APIRouter(tags=["finishes"])


def _get_meet_or_404(db: Session, meet_id: str) -> models.Meet:
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    return meet


@router.get("/api/meets/{meet_id}/finishes", response_model=list[schemas.Finisher])
def list_finishes(meet_id: str, db: Session = Depends(get_db)):
    """All finishes recorded across every race in the meet, in the order
    they were recorded — the activity feed for the Time Entry tab, where
    several races may be finishing concurrently."""
    _get_meet_or_404(db, meet_id)
    return (
        db.query(models.Finisher)
        .join(models.Race, models.Finisher.race_id == models.Race.id)
        .options(
            joinedload(models.Finisher.athlete).joinedload(models.Athlete.team),
            joinedload(models.Finisher.race),
        )
        .filter(models.Race.meet_id == meet_id)
        .order_by(models.Finisher.created_at.asc())
        .all()
    )


@router.post("/api/meets/{meet_id}/finishes", response_model=schemas.Finisher, status_code=201)
def record_finish(meet_id: str, payload: schemas.FinishCreate, db: Session = Depends(get_db)):
    """Record a finish without the operator having to pick a race first:
    the bib is looked up against this meet's athletes, and the athlete's
    assigned race is used. `race_id` is only consulted as a fallback, for a
    no-bib finisher or a bib that doesn't match anyone on the roster."""
    _get_meet_or_404(db, meet_id)

    athlete = resolve_athlete_by_bib(db, meet_id, payload.bib)

    race_id = athlete.race_id if athlete and athlete.race_id else payload.race_id
    if not race_id:
        if athlete:
            detail = (
                f"Bib {payload.bib} matched {athlete.first_name} {athlete.last_name}, "
                "who has no race assigned — specify race_id"
            )
        elif payload.bib:
            detail = f"Bib {payload.bib} did not match any athlete in this meet — specify race_id"
        else:
            detail = "No bib given — specify race_id"
        raise HTTPException(status_code=400, detail=detail)

    race = db.get(models.Race, race_id)
    if not race or race.meet_id != meet_id:
        raise HTTPException(status_code=404, detail="Race not found")

    # The Time Entry tab no longer runs its own stopwatch — it doesn't know
    # the finish time when it can't yet know which race a scanned bib
    # belongs to (that's resolved here). When the caller doesn't supply one,
    # derive it from this race's real start_time, same as the RFID
    # auto-finish path in app/auto_finish.py.
    time_seconds = payload.time_seconds
    if time_seconds is None and race.start_time is not None:
        time_seconds = (datetime.now(timezone.utc) - race.start_time).total_seconds()

    finisher = models.Finisher(
        race_id=race.id,
        athlete_id=athlete.id if athlete else None,
        bib=payload.bib,
        place=next_place(db, race.id),
        time_seconds=time_seconds,
        status=payload.status,
        is_unknown=athlete is None,
        notes=payload.notes,
    )
    db.add(finisher)
    db.commit()
    db.refresh(finisher)
    return finisher


@router.get("/api/finishes", response_model=list[schemas.Finisher])
def list_finishes_for_active_meet(db: Session = Depends(get_db)):
    """Same as GET /api/meets/{meet_id}/finishes, but for whichever meet is
    currently marked active — lets an external device post/list without
    needing to know a meet id."""
    meet = get_active_meet_or_404(db)
    return list_finishes(meet.id, db)


@router.post("/api/finishes", response_model=schemas.Finisher, status_code=201)
def record_finish_for_active_meet(payload: schemas.FinishCreate, db: Session = Depends(get_db)):
    """Same as POST /api/meets/{meet_id}/finishes, but for whichever meet is
    currently marked active."""
    meet = get_active_meet_or_404(db)
    return record_finish(meet.id, payload, db)
