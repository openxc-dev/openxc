import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Meet ----------

class MeetBase(BaseModel):
    name: str
    date: Optional[dt.date] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class MeetCreate(MeetBase):
    pass


class MeetUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[dt.date] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class Meet(MeetBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class MeetSummary(Meet):
    race_count: int = 0
    athlete_count: int = 0


# ---------- Race ----------

class RaceBase(BaseModel):
    name: str
    distance: Optional[str] = None
    scoring_athletes: int = Field(default=5, ge=1)
    displacers: int = Field(default=2, ge=0)


class RaceCreate(RaceBase):
    pass


class RaceUpdate(BaseModel):
    name: Optional[str] = None
    distance: Optional[str] = None
    scoring_athletes: Optional[int] = Field(default=None, ge=1)
    displacers: Optional[int] = Field(default=None, ge=0)
    start_time: Optional[dt.datetime] = None
    finish_time: Optional[dt.datetime] = None


class Race(RaceBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meet_id: str
    slug: str
    start_time: Optional[dt.datetime] = None
    finish_time: Optional[dt.datetime] = None
    created_at: dt.datetime
    updated_at: dt.datetime


class RaceSummary(Race):
    athlete_count: int = 0
    finisher_count: int = 0


# ---------- Team ----------

class TeamBase(BaseModel):
    name: str


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: Optional[str] = None


class Team(TeamBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meet_id: str
    created_at: dt.datetime
    updated_at: dt.datetime


class TeamSummary(Team):
    athlete_count: int = 0


class TeamBulkCreate(BaseModel):
    names: list[str] = Field(min_length=1)


# ---------- Start ----------

class StartCreate(BaseModel):
    """Submitted by the starter (in-app or an external device/system). If
    `time` is omitted, it defaults to the moment the server receives it."""
    label: Optional[str] = None
    time: Optional[dt.datetime] = None


class Start(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meet_id: str
    label: Optional[str] = None
    time: dt.datetime
    created_at: dt.datetime


# ---------- Reader ----------

class ReaderCreate(BaseModel):
    ip_address: str
    label: Optional[str] = None


class Reader(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    ip_address: str
    manufacturer: Optional[str] = None
    product: Optional[str] = None
    serial_number: Optional[str] = None
    num_antennas: Optional[int] = None
    # Antenna IDs (1-based) currently reporting as plugged in — a subset of
    # 1..num_antennas, not the same thing (num_antennas is total ports,
    # regardless of what's connected). None until a successful connect, or
    # if the reader didn't answer this particular query.
    connected_antennas: Optional[list[int]] = None
    status: str
    # Whether a tag-streaming session is actively running right now. This is
    # in-memory process state (see llrp_session.py), not a database column —
    # it does not survive a backend restart, unlike everything else here.
    reading: bool = False
    created_at: dt.datetime
    updated_at: dt.datetime


class ReaderTag(BaseModel):
    tag: str
    antenna_id: Optional[int] = None
    peak_rssi: Optional[int] = None
    time: Optional[dt.datetime] = None


class ReaderTagsResponse(BaseModel):
    reading: bool
    tags: list[ReaderTag]


class StreamTagRead(BaseModel):
    """One entry from the Valkey `livestream` tag-read stream (see
    app/tag_stream.py) — spans all readers, unlike ReaderTag above which is
    one reader's own in-memory buffer."""
    id: str
    event_type: str
    tag: str
    antenna: Optional[int] = None
    rssi: Optional[int] = None
    timestamp: Optional[float] = None
    time: Optional[dt.datetime] = None
    label: str
    reader_id: str


# ---------- Athlete ----------

class AthleteBase(BaseModel):
    bib: str
    first_name: str
    last_name: str
    team_id: Optional[str] = None
    grade: Optional[str] = None
    race_id: Optional[str] = None


class AthleteCreate(AthleteBase):
    pass


class AthleteUpdate(BaseModel):
    bib: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    team_id: Optional[str] = None
    grade: Optional[str] = None
    race_id: Optional[str] = None


class Athlete(AthleteBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    meet_id: str
    created_at: dt.datetime
    updated_at: dt.datetime


class AthleteBulkCreate(BaseModel):
    athletes: list[AthleteCreate]


class AthleteBulkUpdate(BaseModel):
    """Bulk-assign a team and/or race to a set of athletes. Only fields
    actually present in the request are applied — e.g. sending just
    `race_id` leaves each athlete's team untouched."""
    athlete_ids: list[str] = Field(min_length=1)
    team_id: Optional[str] = None
    race_id: Optional[str] = None


# ---------- Finisher / Timing ----------

class FinishCreate(BaseModel):
    """Record a finish without knowing its race up front: the bib is looked
    up against the meet's athletes to find the right race. `race_id` is only
    used as a fallback, when the bib is missing or doesn't match anyone."""
    bib: Optional[str] = None
    race_id: Optional[str] = None
    time_seconds: Optional[float] = None
    status: str = "finished"
    notes: Optional[str] = None


class FinisherUpdate(BaseModel):
    bib: Optional[str] = None
    athlete_id: Optional[str] = None
    time_seconds: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class FinisherReorder(BaseModel):
    ordered_finisher_ids: list[str]


class TeamMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class AthleteMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    bib: str
    first_name: str
    last_name: str
    team: Optional[TeamMini] = None
    grade: Optional[str] = None


class RaceMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str


class Finisher(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    race_id: str
    athlete_id: Optional[str] = None
    bib: Optional[str] = None
    place: int
    time_seconds: Optional[float] = None
    status: str
    is_unknown: bool
    notes: Optional[str] = None
    created_at: dt.datetime
    updated_at: dt.datetime
    athlete: Optional[AthleteMini] = None
    race: Optional[RaceMini] = None


# ---------- Results / Scoring ----------

class IndividualResult(BaseModel):
    place: int
    bib: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    team: Optional[str] = None
    grade: Optional[str] = None
    time_seconds: Optional[float] = None
    status: str
    is_scorer: bool = False
    is_displacer: bool = False
    is_unknown: bool = False


class TeamScoreEntry(BaseModel):
    place: int
    bib: Optional[str] = None
    name: str


class TeamScore(BaseModel):
    team: str
    place: Optional[int] = None
    score: Optional[int] = None
    complete: bool
    scorers: list[TeamScoreEntry]
    displacers: list[TeamScoreEntry]
    runner_count: int


class RaceResults(BaseModel):
    race: Race
    team_scores: list[TeamScore]
    individual_results: list[IndividualResult]


class MeetResults(BaseModel):
    meet: Meet
    races: list[RaceResults]
