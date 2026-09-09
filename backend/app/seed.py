"""Seed a demo meet with races, athletes, and sample finish results.

Run with: python -m app.seed
Safe to re-run: it skips seeding if a meet with the demo name already exists.
"""

import random
from datetime import date

from app import models
from app.database import Base, SessionLocal, engine
from app.slugs import build_meet_id, build_race_slug

DEMO_MEET_NAME = "Riverside Invitational (Demo)"

TEAMS = ["Lincoln HS", "Roosevelt HS", "Jefferson HS", "Washington HS", "Madison HS"]

FIRST_NAMES = [
    "Ava", "Liam", "Emma", "Noah", "Olivia", "Ethan", "Sophia", "Mason",
    "Isabella", "Lucas", "Mia", "Logan", "Amelia", "Jack", "Harper", "Owen",
    "Evelyn", "Wyatt", "Abigail", "Caleb", "Ella", "Ryan", "Grace", "Luke",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
]


def seed_demo_meet(db):
    existing = db.query(models.Meet).filter(models.Meet.name == DEMO_MEET_NAME).first()
    if existing:
        print(f"Demo meet already exists: {existing.id}")
        return existing

    rng = random.Random(42)

    meet_date = date.today()
    meet = models.Meet(
        id=build_meet_id(db, DEMO_MEET_NAME, meet_date),
        name=DEMO_MEET_NAME,
        date=meet_date,
        location="Riverside Park",
        notes="Auto-generated demo data for testing the timing workflow.",
    )
    db.add(meet)
    db.flush()

    team_by_name = {}
    for team_name in TEAMS:
        team = models.Team(meet_id=meet.id, name=team_name)
        db.add(team)
        team_by_name[team_name] = team
    db.flush()

    races_config = [
        ("Boys Varsity", "5000m", 7, 2),
        ("Girls Varsity", "5000m", 7, 2),
        ("Boys JV", "5000m", 5, 2),
    ]

    bib_counter = 100
    for race_name, distance, per_team, _unused in races_config:
        race = models.Race(
            meet_id=meet.id,
            name=race_name,
            slug=build_race_slug(db, meet.id, race_name),
            distance=distance,
            scoring_athletes=5,
            displacers=2,
        )
        db.add(race)
        db.flush()

        athletes = []
        for team in TEAMS:
            roster_size = rng.randint(per_team - 1, per_team + 2)
            for _ in range(roster_size):
                bib_counter += 1
                athlete = models.Athlete(
                    meet_id=meet.id,
                    race_id=race.id,
                    bib=str(bib_counter),
                    first_name=rng.choice(FIRST_NAMES),
                    last_name=rng.choice(LAST_NAMES),
                    team_id=team_by_name[team].id,
                    grade=str(rng.choice([9, 10, 11, 12])),
                )
                db.add(athlete)
                athletes.append(athlete)
        db.flush()

        rng.shuffle(athletes)
        base_time = 15 * 60
        place = 1
        for athlete in athletes:
            base_time += rng.randint(3, 25)
            finisher = models.Finisher(
                race_id=race.id,
                athlete_id=athlete.id,
                bib=athlete.bib,
                place=place,
                time_seconds=float(base_time),
                status=models.FinishStatus.FINISHED.value,
                is_unknown=False,
            )
            db.add(finisher)
            place += 1

    db.commit()
    print(f"Seeded demo meet {meet.id} with {len(races_config)} races.")
    return meet


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_demo_meet(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
