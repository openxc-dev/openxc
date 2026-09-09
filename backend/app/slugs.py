import re
import unicodedata
from datetime import date, datetime

from sqlalchemy.orm import Session

from app import models


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "meet"


def build_meet_id(db: Session, name: str, meet_date: date | None) -> str:
    """e.g. "Really Big Invitational" + 2026 -> "really_big_invitational_2026".

    Falls back to the current year when no meet date is given, and
    disambiguates collisions (same name + year) with a "-2", "-3", ... suffix.
    """
    year = meet_date.year if meet_date else datetime.now().year
    base = f"{slugify(name)}_{year}"

    candidate = base
    suffix = 2
    while db.get(models.Meet, candidate) is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def build_race_slug(db: Session, meet_id: str, name: str) -> str:
    """e.g. "Boys Varsity" -> "boys_varsity", unique within the meet.

    Used for the public race results URL: /{meet_slug}/{race_slug}.
    Disambiguates collisions (same name reused within a meet) with a
    "-2", "-3", ... suffix.
    """
    base = slugify(name)

    candidate = base
    suffix = 2
    while (
        db.query(models.Race)
        .filter(models.Race.meet_id == meet_id, models.Race.slug == candidate)
        .first()
        is not None
    ):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
