from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.finishers import close_place_gap, resolve_athlete_by_bib

router = APIRouter(tags=["timing"])


def _get_race_or_404(db: Session, race_id: str) -> models.Race:
    race = db.get(models.Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    return race


def _finisher_query(db: Session, race_id: str):
    return (
        db.query(models.Finisher)
        .options(
            joinedload(models.Finisher.athlete).joinedload(models.Athlete.team),
            joinedload(models.Finisher.race),
        )
        .filter(models.Finisher.race_id == race_id)
    )


@router.get("/api/races/{race_id}/finishers", response_model=list[schemas.Finisher])
def list_finishers(race_id: str, db: Session = Depends(get_db)):
    _get_race_or_404(db, race_id)
    return _finisher_query(db, race_id).order_by(models.Finisher.place).all()


@router.patch("/api/finishers/{finisher_id}", response_model=schemas.Finisher)
def update_finisher(finisher_id: str, payload: schemas.FinisherUpdate, db: Session = Depends(get_db)):
    finisher = db.get(models.Finisher, finisher_id)
    if not finisher:
        raise HTTPException(status_code=404, detail="Finisher not found")

    race = db.get(models.Race, finisher.race_id)
    data = payload.model_dump(exclude_unset=True)

    if "athlete_id" in data:
        finisher.athlete_id = data["athlete_id"]
        finisher.is_unknown = data["athlete_id"] is None
    elif "bib" in data:
        athlete = resolve_athlete_by_bib(db, race.meet_id, data["bib"])
        finisher.athlete_id = athlete.id if athlete else None
        finisher.is_unknown = athlete is None

    if "bib" in data:
        finisher.bib = data["bib"]
    if "time_seconds" in data:
        finisher.time_seconds = data["time_seconds"]
    if "status" in data:
        finisher.status = data["status"]
    if "notes" in data:
        finisher.notes = data["notes"]

    db.commit()
    db.refresh(finisher)
    return finisher


@router.delete("/api/finishers/{finisher_id}", status_code=204)
def delete_finisher(finisher_id: str, db: Session = Depends(get_db)):
    finisher = db.get(models.Finisher, finisher_id)
    if not finisher:
        raise HTTPException(status_code=404, detail="Finisher not found")

    race_id = finisher.race_id
    removed_place = finisher.place
    db.delete(finisher)
    db.flush()

    close_place_gap(db, race_id, removed_place)

    db.commit()
    return None


@router.post("/api/races/{race_id}/finishers/reorder", response_model=list[schemas.Finisher])
def reorder_finishers(race_id: str, payload: schemas.FinisherReorder, db: Session = Depends(get_db)):
    _get_race_or_404(db, race_id)
    finishers = _finisher_query(db, race_id).all()
    by_id = {f.id: f for f in finishers}

    if set(payload.ordered_finisher_ids) != set(by_id.keys()):
        raise HTTPException(status_code=400, detail="ordered_finisher_ids must include all finishers in the race exactly once")

    for f in finishers:
        f.place = -(f.place)
    db.flush()

    for idx, finisher_id in enumerate(payload.ordered_finisher_ids, start=1):
        by_id[finisher_id].place = idx

    db.commit()
    return _finisher_query(db, race_id).order_by(models.Finisher.place).all()
