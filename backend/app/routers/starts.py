from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.meets import get_active_meet_or_404

router = APIRouter(tags=["starts"])


def _get_meet_or_404(db: Session, meet_id: str) -> models.Meet:
    meet = db.get(models.Meet, meet_id)
    if not meet:
        raise HTTPException(status_code=404, detail="Meet not found")
    return meet


@router.get("/api/meets/{meet_id}/starts", response_model=list[schemas.Start])
def list_starts(meet_id: str, db: Session = Depends(get_db)):
    _get_meet_or_404(db, meet_id)
    return (
        db.query(models.Start)
        .filter(models.Start.meet_id == meet_id)
        .order_by(models.Start.time.desc())
        .all()
    )


@router.post("/api/meets/{meet_id}/starts", response_model=schemas.Start, status_code=201)
def create_start(meet_id: str, payload: schemas.StartCreate, db: Session = Depends(get_db)):
    """Submit a start record. Meant to be callable by an external starter
    device/system as well as the in-app UI. `time` defaults to now (server
    clock) when omitted, so a simple fire-and-forget POST at gun time works."""
    _get_meet_or_404(db, meet_id)
    start = models.Start(
        meet_id=meet_id,
        label=payload.label,
        time=payload.time or datetime.now(timezone.utc),
    )
    db.add(start)
    db.commit()
    db.refresh(start)
    return start


@router.get("/api/starts", response_model=list[schemas.Start])
def list_starts_for_active_meet(db: Session = Depends(get_db)):
    """Same as GET /api/meets/{meet_id}/starts, but for whichever meet is
    currently marked active — lets an external starter device post/list
    without needing to know a meet id."""
    meet = get_active_meet_or_404(db)
    return list_starts(meet.id, db)


@router.post("/api/starts", response_model=schemas.Start, status_code=201)
def create_start_for_active_meet(payload: schemas.StartCreate, db: Session = Depends(get_db)):
    """Same as POST /api/meets/{meet_id}/starts, but for whichever meet is
    currently marked active."""
    meet = get_active_meet_or_404(db)
    return create_start(meet.id, payload, db)


@router.delete("/api/starts/{start_id}", status_code=204)
def delete_start(start_id: str, db: Session = Depends(get_db)):
    start = db.get(models.Start, start_id)
    if not start:
        raise HTTPException(status_code=404, detail="Start not found")
    db.delete(start)
    db.commit()
    return None
