from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(tags=["teams"])


def _get_meet_or_404(db: Session, meet_id: str) -> models.Meet:
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    return meet


@router.get("/api/meets/{meet_id}/teams", response_model=list[schemas.TeamSummary])
def list_teams(meet_id: str, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    teams = db.query(models.Team).filter(models.Team.meet_id == meet_id).order_by(models.Team.name).all()
    summaries = []
    for t in teams:
        athlete_count = db.query(func.count(models.Athlete.id)).filter(models.Athlete.team_id == t.id).scalar()
        summaries.append(
            schemas.TeamSummary(**schemas.Team.model_validate(t).model_dump(), athlete_count=athlete_count)
        )
    return summaries


@router.post("/api/meets/{meet_id}/teams", response_model=schemas.Team, status_code=201)
def create_team(meet_id: str, payload: schemas.TeamCreate, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")
    team = models.Team(meet_id=meet_id, name=name)
    db.add(team)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'Team "{name}" already exists in this meet')
    db.refresh(team)
    return team


@router.post("/api/meets/{meet_id}/teams/bulk", response_model=list[schemas.Team], status_code=201)
def bulk_create_teams(meet_id: str, payload: schemas.TeamBulkCreate, db: Session = Depends(get_db)):
    """Add several teams at once, skipping any name that already exists in
    this meet (case-insensitive) or is repeated within the submitted list."""
    _get_meet_or_404(db, meet_id)
    existing_lower = {
        t.name.lower() for t in db.query(models.Team.name).filter(models.Team.meet_id == meet_id)
    }
    created = []
    seen_lower = set()
    for raw_name in payload.names:
        name = raw_name.strip()
        if not name:
            continue
        lower = name.lower()
        if lower in existing_lower or lower in seen_lower:
            continue
        seen_lower.add(lower)
        team = models.Team(meet_id=meet_id, name=name)
        db.add(team)
        created.append(team)
    if not created:
        return []
    db.commit()
    for t in created:
        db.refresh(t)
    return created


@router.patch("/api/teams/{team_id}", response_model=schemas.Team)
def update_team(team_id: str, payload: schemas.TeamUpdate, db: Session = Depends(get_db)):
    team = db.get(models.Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Team name is required")
        data["name"] = name
    for key, value in data.items():
        setattr(team, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f'Team "{data.get("name")}" already exists in this meet')
    db.refresh(team)
    return team


@router.delete("/api/teams/{team_id}", status_code=204)
def delete_team(team_id: str, db: Session = Depends(get_db)):
    team = db.get(models.Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete(team)
    db.commit()
    return None
