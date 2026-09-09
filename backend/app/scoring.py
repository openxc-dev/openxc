"""Standard cross country team scoring.

Rules implemented:
- Individual place is the true finish order (1..N) across the whole race,
  including unattached / unknown runners and DNF/DQ excluded from place math.
- A team's score is the sum of the race-places of its top N runners
  (N = race.scoring_athletes), where N is ordered by each runner's place.
- A team must have at least N finishers to receive a score ("complete").
  Incomplete teams are still listed but do not receive a place/score.
- The next D runners per team (D = race.displacers) are "displacers": they
  do not count toward the score but are used to break ties (the classic
  "6th runner" rule), compared displacer-by-displacer.
- Teams are ranked by score ascending; ties broken by comparing displacers
  in order (first displacer's place, then second, ...); remaining ties are
  a true tie and share a place.
"""

from dataclasses import dataclass, field

from app import models, schemas


@dataclass
class _TeamRunners:
    team: str
    runners: list["models.Finisher"] = field(default_factory=list)


def _athlete_name(finisher: models.Finisher) -> tuple[str | None, str | None]:
    if finisher.athlete:
        return finisher.athlete.first_name, finisher.athlete.last_name
    return None, None


def _team_name(finisher: models.Finisher) -> str | None:
    if finisher.athlete and finisher.athlete.team:
        return finisher.athlete.team.name
    return None


def build_individual_results(
    finishers: list[models.Finisher], race: models.Race
) -> list[schemas.IndividualResult]:
    scoring_slots, displacer_slots = _compute_scorer_and_displacer_ids(finishers, race)

    results = []
    for f in finishers:
        first, last = _athlete_name(f)
        team = _team_name(f)
        results.append(
            schemas.IndividualResult(
                place=f.place,
                bib=f.bib,
                first_name=first,
                last_name=last,
                team=team,
                grade=f.athlete.grade if f.athlete else None,
                time_seconds=f.time_seconds,
                status=f.status,
                is_scorer=f.id in scoring_slots,
                is_displacer=f.id in displacer_slots,
                is_unknown=f.is_unknown or f.athlete_id is None,
            )
        )
    return results


def _compute_scorer_and_displacer_ids(
    finishers: list[models.Finisher], race: models.Race
) -> tuple[set, set]:
    by_team: dict[str, list[models.Finisher]] = {}
    for f in finishers:
        if f.status != models.FinishStatus.FINISHED.value:
            continue
        team_name = _team_name(f)
        if not team_name:
            continue
        by_team.setdefault(team_name, []).append(f)

    scorer_ids: set = set()
    displacer_ids: set = set()
    for team, runners in by_team.items():
        ordered = sorted(runners, key=lambda r: r.place)
        scorers = ordered[: race.scoring_athletes]
        displacers = ordered[race.scoring_athletes : race.scoring_athletes + race.displacers]
        scorer_ids.update(r.id for r in scorers)
        displacer_ids.update(r.id for r in displacers)

    return scorer_ids, displacer_ids


def build_team_scores(
    finishers: list[models.Finisher], race: models.Race
) -> list[schemas.TeamScore]:
    by_team: dict[str, list[models.Finisher]] = {}
    for f in finishers:
        if f.status != models.FinishStatus.FINISHED.value:
            continue
        team_name = _team_name(f)
        if not team_name:
            continue
        by_team.setdefault(team_name, []).append(f)

    entries: list[dict] = []
    for team, runners in by_team.items():
        ordered = sorted(runners, key=lambda r: r.place)
        scorers = ordered[: race.scoring_athletes]
        displacers = ordered[race.scoring_athletes : race.scoring_athletes + race.displacers]
        complete = len(ordered) >= race.scoring_athletes
        score = sum(r.place for r in scorers) if complete else None
        entries.append(
            {
                "team": team,
                "complete": complete,
                "score": score,
                "scorers": scorers,
                "displacers": displacers,
                "runner_count": len(ordered),
                "tiebreak": [r.place for r in displacers],
            }
        )

    complete_entries = [e for e in entries if e["complete"]]
    incomplete_entries = [e for e in entries if not e["complete"]]

    complete_entries.sort(key=lambda e: (e["score"], e["tiebreak"]))
    incomplete_entries.sort(key=lambda e: (-e["runner_count"], e["team"]))

    results = []
    place = 0
    prev_key = None
    for e in complete_entries:
        key = (e["score"], tuple(e["tiebreak"]))
        place += 1
        if key == prev_key:
            assigned_place = results[-1].place
        else:
            assigned_place = place
        prev_key = key
        results.append(
            schemas.TeamScore(
                team=e["team"],
                place=assigned_place,
                score=e["score"],
                complete=True,
                scorers=[_to_entry(r) for r in e["scorers"]],
                displacers=[_to_entry(r) for r in e["displacers"]],
                runner_count=e["runner_count"],
            )
        )

    for e in incomplete_entries:
        results.append(
            schemas.TeamScore(
                team=e["team"],
                place=None,
                score=None,
                complete=False,
                scorers=[_to_entry(r) for r in e["scorers"]],
                displacers=[_to_entry(r) for r in e["displacers"]],
                runner_count=e["runner_count"],
            )
        )

    return results


def _to_entry(f: models.Finisher) -> schemas.TeamScoreEntry:
    name = "Unknown"
    if f.athlete:
        name = f"{f.athlete.first_name} {f.athlete.last_name}"
    return schemas.TeamScoreEntry(place=f.place, bib=f.bib, name=name)


def build_race_results(race: models.Race, finishers: list[models.Finisher]) -> schemas.RaceResults:
    ordered = sorted(finishers, key=lambda f: f.place)
    return schemas.RaceResults(
        race=schemas.Race.model_validate(race),
        team_scores=build_team_scores(ordered, race),
        individual_results=build_individual_results(ordered, race),
    )
