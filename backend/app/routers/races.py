from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.slugs import build_race_slug

router = APIRouter(tags=["races"])


def _get_meet_or_404(db: Session, meet_id: str) -> models.Meet:
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    return meet


@router.get("/api/meets/{meet_id}/races", response_model=list[schemas.RaceSummary])
def list_races(meet_id: str, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    races = db.query(models.Race).filter(models.Race.meet_id == meet_id).order_by(models.Race.name).all()
    summaries = []
    for r in races:
        athlete_count = db.query(func.count(models.Athlete.id)).filter(models.Athlete.race_id == r.id).scalar()
        finisher_count = db.query(func.count(models.Finisher.id)).filter(models.Finisher.race_id == r.id).scalar()
        summaries.append(
            schemas.RaceSummary(
                **schemas.Race.model_validate(r).model_dump(),
                athlete_count=athlete_count,
                finisher_count=finisher_count,
            )
        )
    return summaries


@router.post("/api/meets/{meet_id}/races", response_model=schemas.Race, status_code=201)
def create_race(meet_id: str, payload: schemas.RaceCreate, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    slug = build_race_slug(db, meet_id, payload.name)
    race = models.Race(meet_id=meet_id, slug=slug, **payload.model_dump())
    db.add(race)
    db.commit()
    db.refresh(race)
    return race


@router.get("/api/races/{race_id}", response_model=schemas.Race)
def get_race(race_id: str, db: Session = Depends(get_db)):
    race = db.get(models.Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    return race


@router.patch("/api/races/{race_id}", response_model=schemas.Race)
def update_race(race_id: str, payload: schemas.RaceUpdate, db: Session = Depends(get_db)):
    race = db.get(models.Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    data = payload.model_dump(exclude_unset=True)

    resulting_start = data.get("start_time", race.start_time)
    resulting_finish = data.get("finish_time", race.finish_time)
    if resulting_finish is not None:
        if resulting_start is None:
            raise HTTPException(status_code=400, detail="Race must be started before it can be finished")
        if resulting_finish < resulting_start:
            raise HTTPException(status_code=400, detail="Finish time cannot be before the start time")

    for key, value in data.items():
        setattr(race, key, value)
    db.commit()
    db.refresh(race)
    return race


@router.delete("/api/races/{race_id}", status_code=204)
def delete_race(race_id: str, db: Session = Depends(get_db)):
    race = db.get(models.Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    db.delete(race)
    db.commit()
    return None
