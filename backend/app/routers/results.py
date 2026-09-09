from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.scoring import build_race_results

router = APIRouter(tags=["results"])


def _race_results(db: Session, race: models.Race) -> schemas.RaceResults:
    finishers = (
        db.query(models.Finisher)
        .options(joinedload(models.Finisher.athlete).joinedload(models.Athlete.team))
        .filter(models.Finisher.race_id == race.id)
        .order_by(models.Finisher.place)
        .all()
    )
    return build_race_results(race, finishers)


@router.get("/api/races/{race_id}/results", response_model=schemas.RaceResults)
def race_results(race_id: str, db: Session = Depends(get_db)):
    race = db.get(models.Race, race_id)
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    return _race_results(db, race)


@router.get("/api/meets/{meet_id}/races/{race_slug}/results", response_model=schemas.RaceResults)
def race_results_by_slug(meet_id: str, race_slug: str, db: Session = Depends(get_db)):
    race = (
        db.query(models.Race)
        .filter(models.Race.meet_id == meet_id, models.Race.slug == race_slug)
        .first()
    )
    if not race:
        raise HTTPException(status_code=404, detail="Race not found")
    return _race_results(db, race)


@router.get("/api/meets/{meet_id}/results", response_model=schemas.MeetResults)
def meet_results(meet_id: str, db: Session = Depends(get_db)):
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    races = db.query(models.Race).filter(models.Race.meet_id == meet_id).order_by(models.Race.name).all()
    return schemas.MeetResults(
        meet=schemas.Meet.model_validate(meet),
        races=[_race_results(db, r) for r in races],
    )
