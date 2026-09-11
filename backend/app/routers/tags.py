from fastapi import APIRouter, Query

from app import schemas
from app.tag_stream import read_recent

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[schemas.StreamTagRead])
def list_tags(seconds: float = Query(default=5.0, gt=0, description="How far back to look, in seconds.")):
    """Tag reads from the Valkey `livestream` stream across all readers,
    oldest first. Defaults to the last 5 seconds; pass ?seconds= to widen or
    narrow the window."""
    return read_recent(seconds)
