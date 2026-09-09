from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.slugs import build_meet_id

router = APIRouter(prefix="/api/meets", tags=["meets"])


def get_active_meet_or_404(db: Session) -> models.Meet:
    """Shared by the meet-agnostic /api/finishes and /api/starts endpoints,
    which resolve to whichever meet is currently marked active."""
    meet = db.query(models.Meet).filter(models.Meet.is_active.is_(True)).first()
    if not meet:
        raise HTTPException(status_code=404, detail="No active meet set")
    return meet


@router.get("", response_model=list[schemas.MeetSummary])
def list_meets(db: Session = Depends(get_db)):
    meets = db.query(models.Meet).order_by(models.Meet.date.desc().nullslast(), models.Meet.name).all()
    summaries = []
    for m in meets:
        race_count = db.query(func.count(models.Race.id)).filter(models.Race.meet_id == m.id).scalar()
        athlete_count = db.query(func.count(models.Athlete.id)).filter(models.Athlete.meet_id == m.id).scalar()
        summaries.append(
            schemas.MeetSummary(
                **schemas.Meet.model_validate(m).model_dump(),
                race_count=race_count,
                athlete_count=athlete_count,
            )
        )
    return summaries


@router.post("", response_model=schemas.Meet, status_code=201)
def create_meet(payload: schemas.MeetCreate, db: Session = Depends(get_db)):
    meet_id = build_meet_id(db, payload.name, payload.date)
    meet = models.Meet(id=meet_id, **payload.model_dump())
    db.add(meet)
    db.commit()
    db.refresh(meet)
    return meet


@router.get("/active", response_model=schemas.Meet)
def get_active_meet(db: Session = Depends(get_db)):
    # Must be registered before GET /{meet_id} — "active" would otherwise be
    # swallowed by that route as a literal (and invalid) meet_id.
    return get_active_meet_or_404(db)


@router.get("/{meet_id}", response_model=schemas.Meet)
def get_meet(meet_id: str, db: Session = Depends(get_db)):
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    return meet


@router.patch("/{meet_id}", response_model=schemas.Meet)
def update_meet(meet_id: str, payload: schemas.MeetUpdate, db: Session = Depends(get_db)):
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_active") is True:
        # Only one meet can be active — deactivate any other before setting
        # this one, so the DB's partial unique index never gets a chance to
        # reject it.
        db.query(models.Meet).filter(models.Meet.id != meet_id, models.Meet.is_active.is_(True)).update(
            {"is_active": False}, synchronize_session=False
        )
    for key, value in data.items():
        setattr(meet, key, value)
    db.commit()
    db.refresh(meet)
    return meet


@router.delete("/{meet_id}", status_code=204)
def delete_meet(meet_id: str, db: Session = Depends(get_db)):
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    db.delete(meet)
    db.commit()
    return None
