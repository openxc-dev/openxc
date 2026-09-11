import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class FinishStatus(str, enum.Enum):
    FINISHED = "finished"
    DNF = "dnf"
    DQ = "dq"


class ReaderStatus(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class Meet(Base):
    __tablename__ = "meets"
    __table_args__ = (
        # Defense in depth alongside the application-level logic in
        # routers/meets.py that clears other meets before activating one:
        # the database itself refuses to have two active meets at once.
        Index(
            "uq_meets_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    date = Column(Date, nullable=True)
    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    races = relationship("Race", back_populates="meet", cascade="all, delete-orphan", order_by="Race.name")
    teams = relationship("Team", back_populates="meet", cascade="all, delete-orphan", order_by="Team.name")
    athletes = relationship("Athlete", back_populates="meet", cascade="all, delete-orphan")
    starts = relationship("Start", back_populates="meet", cascade="all, delete-orphan", order_by="Start.time.desc()")


class Race(Base):
    __tablename__ = "races"
    __table_args__ = (UniqueConstraint("meet_id", "slug", name="uq_race_meet_slug"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    meet_id = Column(String(255), ForeignKey("meets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    distance = Column(String(50), nullable=True)
    scoring_athletes = Column(Integer, nullable=False, default=5)
    displacers = Column(Integer, nullable=False, default=2)
    start_time = Column(DateTime(timezone=True), nullable=True)
    finish_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    meet = relationship("Meet", back_populates="races")
    athletes = relationship("Athlete", back_populates="race")
    finishers = relationship("Finisher", back_populates="race", cascade="all, delete-orphan")


class Start(Base):
    __tablename__ = "starts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    meet_id = Column(String(255), ForeignKey("meets.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(255), nullable=True)
    time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meet = relationship("Meet", back_populates="starts")


class Reader(Base):
    """An LLRP RFID reader registered for finish-line tag acquisition. Not
    meet-scoped — a physical reader is a piece of hardware you plug in and
    reuse across meets, not something that belongs to one. `manufacturer`,
    `product`, `serial_number`, `num_antennas`, and `connected_antennas` are
    populated from the reader's own capabilities once a real connection is
    established; they're blank until then. `num_antennas` is the reader's
    total antenna port count (hardware capability) — `connected_antennas`
    is which of those ports actually have an antenna plugged in right now,
    which can be fewer; the two are not the same thing."""

    __tablename__ = "readers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    label = Column(String(255), nullable=False, unique=True)
    ip_address = Column(String(45), nullable=False)
    manufacturer = Column(String(255), nullable=True)
    product = Column(String(255), nullable=True)
    serial_number = Column(String(255), nullable=True)
    num_antennas = Column(Integer, nullable=True)
    connected_antennas = Column(ARRAY(Integer), nullable=True)
    status = Column(String(20), nullable=False, default=ReaderStatus.DISCONNECTED.value)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("meet_id", "name", name="uq_team_meet_name"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    meet_id = Column(String(255), ForeignKey("meets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    meet = relationship("Meet", back_populates="teams")
    athletes = relationship("Athlete", back_populates="team")


class Athlete(Base):
    __tablename__ = "athletes"
    __table_args__ = (UniqueConstraint("meet_id", "bib", name="uq_athlete_meet_bib"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    meet_id = Column(String(255), ForeignKey("meets.id", ondelete="CASCADE"), nullable=False)
    race_id = Column(UUID(as_uuid=False), ForeignKey("races.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID(as_uuid=False), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    bib = Column(String(20), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    grade = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    meet = relationship("Meet", back_populates="athletes")
    race = relationship("Race", back_populates="athletes")
    team = relationship("Team", back_populates="athletes")
    finishers = relationship("Finisher", back_populates="athlete")


class Finisher(Base):
    __tablename__ = "finishers"
    __table_args__ = (UniqueConstraint("race_id", "place", name="uq_finisher_race_place"),)

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    race_id = Column(UUID(as_uuid=False), ForeignKey("races.id", ondelete="CASCADE"), nullable=False)
    athlete_id = Column(UUID(as_uuid=False), ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True)
    bib = Column(String(20), nullable=True)
    place = Column(Integer, nullable=False)
    time_seconds = Column(Float, nullable=True)
    status = Column(String(10), nullable=False, default=FinishStatus.FINISHED.value)
    is_unknown = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    race = relationship("Race", back_populates="finishers")
    athlete = relationship("Athlete", back_populates="finishers")
