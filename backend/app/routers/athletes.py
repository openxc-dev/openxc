from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.finishers import reassign_athlete_finishers

router = APIRouter(tags=["athletes"])


def _get_meet_or_404(db: Session, meet_id: str) -> models.Meet:
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    return meet


def _check_race_in_meet_or_404(db: Session, meet_id: str, race_id: str) -> None:
    race = db.get(models.Race, race_id)
    if not race or race.meet_id != meet_id:
        raise HTTPException(status_code=404, detail="Race not found")


def _check_team_in_meet_or_404(db: Session, meet_id: str, team_id: str) -> None:
    team = db.get(models.Team, team_id)
    if not team or team.meet_id != meet_id:
        raise HTTPException(status_code=404, detail="Team not found")


@router.get("/api/meets/{meet_id}/athletes", response_model=list[schemas.Athlete])
def list_athletes(
    meet_id: str,
    race_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_meet_or_404(db, meet_id)
    q = db.query(models.Athlete).filter(models.Athlete.meet_id == meet_id)
    if race_id:
        q = q.filter(models.Athlete.race_id == race_id)
    if team_id:
        q = q.filter(models.Athlete.team_id == team_id)
    if search:
        like = f"%{search.lower()}%"
        q = q.outerjoin(models.Team, models.Athlete.team_id == models.Team.id).filter(
            (models.Athlete.first_name.ilike(like))
            | (models.Athlete.last_name.ilike(like))
            | (models.Athlete.bib.ilike(like))
            | (models.Team.name.ilike(like))
        )
    return q.order_by(models.Athlete.bib).all()


@router.post("/api/meets/{meet_id}/athletes", response_model=schemas.Athlete, status_code=201)
def create_athlete(meet_id: str, payload: schemas.AthleteCreate, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    if payload.race_id:
        _check_race_in_meet_or_404(db, meet_id, payload.race_id)
    if payload.team_id:
        _check_team_in_meet_or_404(db, meet_id, payload.team_id)
    athlete = models.Athlete(meet_id=meet_id, **payload.model_dump())
    db.add(athlete)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Bib {payload.bib} already used in this meet")
    db.refresh(athlete)
    return athlete


@router.post("/api/meets/{meet_id}/athletes/bulk", response_model=list[schemas.Athlete], status_code=201)
def bulk_create_athletes(meet_id: str, payload: schemas.AthleteBulkCreate, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    valid_race_ids = {r.id for r in db.query(models.Race.id).filter(models.Race.meet_id == meet_id)}
    valid_team_ids = {t.id for t in db.query(models.Team.id).filter(models.Team.meet_id == meet_id)}
    created = []
    seen_bibs = set()
    for item in payload.athletes:
        if item.bib in seen_bibs:
            raise HTTPException(status_code=409, detail=f"Duplicate bib {item.bib} in submitted batch")
        seen_bibs.add(item.bib)
        if item.race_id and item.race_id not in valid_race_ids:
            raise HTTPException(status_code=404, detail=f"Race not found: {item.race_id}")
        if item.team_id and item.team_id not in valid_team_ids:
            raise HTTPException(status_code=404, detail=f"Team not found: {item.team_id}")
        athlete = models.Athlete(meet_id=meet_id, **item.model_dump())
        db.add(athlete)
        created.append(athlete)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="One or more bibs already used in this meet")
    for a in created:
        db.refresh(a)
    return created


@router.patch("/api/meets/{meet_id}/athletes/bulk", response_model=list[schemas.Athlete])
def bulk_update_athletes(meet_id: str, payload: schemas.AthleteBulkUpdate, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    data = payload.model_dump(exclude_unset=True, exclude={"athlete_ids"})
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update — provide team_id and/or race_id")
    if data.get("team_id"):
        _check_team_in_meet_or_404(db, meet_id, data["team_id"])
    if data.get("race_id"):
        _check_race_in_meet_or_404(db, meet_id, data["race_id"])

    ids = set(payload.athlete_ids)
    athletes = (
        db.query(models.Athlete)
        .filter(models.Athlete.meet_id == meet_id, models.Athlete.id.in_(ids))
        .all()
    )
    if len(athletes) != len(ids):
        raise HTTPException(status_code=404, detail="One or more athletes not found in this meet")

    for athlete in athletes:
        for key, value in data.items():
            setattr(athlete, key, value)

    if "race_id" in data:
        db.flush()
        for athlete in athletes:
            reassign_athlete_finishers(db, athlete.id, data["race_id"])

    db.commit()
    for athlete in athletes:
        db.refresh(athlete)
    return athletes


@router.get("/api/athletes/{athlete_id}", response_model=schemas.Athlete)
def get_athlete(athlete_id: str, db: Session = Depends(get_db)):
    athlete = db.get(models.Athlete, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return athlete


@router.patch("/api/athletes/{athlete_id}", response_model=schemas.Athlete)
def update_athlete(athlete_id: str, payload: schemas.AthleteUpdate, db: Session = Depends(get_db)):
    athlete = db.get(models.Athlete, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("race_id"):
        _check_race_in_meet_or_404(db, athlete.meet_id, data["race_id"])
    if data.get("team_id"):
        _check_team_in_meet_or_404(db, athlete.meet_id, data["team_id"])
    for key, value in data.items():
        setattr(athlete, key, value)
    if "race_id" in data:
        db.flush()
        reassign_athlete_finishers(db, athlete.id, data["race_id"])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bib already used in this meet")
    db.refresh(athlete)
    return athlete


@router.delete("/api/athletes/{athlete_id}", status_code=204)
def delete_athlete(athlete_id: str, db: Session = Depends(get_db)):
    athlete = db.get(models.Athlete, athlete_id)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")
    db.delete(athlete)
    db.commit()
    return None
