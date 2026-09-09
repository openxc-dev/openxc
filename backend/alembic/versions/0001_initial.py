"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meets",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "uq_meets_single_active",
        "meets",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "races",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("meet_id", sa.String(length=255), sa.ForeignKey("meets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("distance", sa.String(length=50), nullable=True),
        sa.Column("scoring_athletes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("displacers", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finish_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("meet_id", "slug", name="uq_race_meet_slug"),
    )
    op.create_index("ix_races_meet_id", "races", ["meet_id"])

    op.create_table(
        "starts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("meet_id", sa.String(length=255), sa.ForeignKey("meets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_starts_meet_id", "starts", ["meet_id"])

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("meet_id", sa.String(length=255), sa.ForeignKey("meets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("meet_id", "name", name="uq_team_meet_name"),
    )
    op.create_index("ix_teams_meet_id", "teams", ["meet_id"])

    op.create_table(
        "athletes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("meet_id", sa.String(length=255), sa.ForeignKey("meets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("race_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("races.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bib", sa.String(length=20), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("grade", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("meet_id", "bib", name="uq_athlete_meet_bib"),
    )
    op.create_index("ix_athletes_meet_id", "athletes", ["meet_id"])
    op.create_index("ix_athletes_race_id", "athletes", ["race_id"])
    op.create_index("ix_athletes_team_id", "athletes", ["team_id"])

    op.create_table(
        "finishers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("race_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("races.id", ondelete="CASCADE"), nullable=False),
        sa.Column("athlete_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bib", sa.String(length=20), nullable=True),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("time_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="finished"),
        sa.Column("is_unknown", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("race_id", "place", name="uq_finisher_race_place"),
    )
    op.create_index("ix_finishers_race_id", "finishers", ["race_id"])
    op.create_index("ix_finishers_athlete_id", "finishers", ["athlete_id"])

    op.create_table(
        "readers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("label", sa.String(length=255), nullable=False, unique=True),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=True),
        sa.Column("product", sa.String(length=255), nullable=True),
        sa.Column("num_antennas", sa.Integer(), nullable=True),
        sa.Column("connected_antennas", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="disconnected"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("readers")
    op.drop_table("finishers")
    op.drop_table("athletes")
    op.drop_table("teams")
    op.drop_table("starts")
    op.drop_table("races")
    op.drop_table("meets")
