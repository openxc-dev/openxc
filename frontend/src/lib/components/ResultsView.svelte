<script>
	import { formatTime, ordinal } from '../format';

	export let raceResults;
	export let showRaceLink = false;
</script>

<div class="race-results">
	<div class="race-results-header">
		<h3>{raceResults.race.name}</h3>
		{#if raceResults.race.distance}<span class="badge">{raceResults.race.distance}</span>{/if}
		<span class="badge">Top {raceResults.race.scoring_athletes} score, {raceResults.race.displacers} displacers</span>
		{#if showRaceLink}
			<a class="race-link" href="/{raceResults.race.meet_id}/{raceResults.race.slug}" target="_blank" rel="noreferrer">
				Race page ↗
			</a>
		{/if}
	</div>

	<div class="results-grid">
		<div class="panel">
			<h4>Team Scores</h4>
			{#if raceResults.team_scores.length === 0}
				<p class="muted">No team scores yet — record finishers with team-assigned athletes.</p>
			{:else}
				<table>
					<thead>
						<tr>
							<th>Place</th>
							<th>Team</th>
							<th>Score</th>
							<th>Scorers (place)</th>
							<th>Displacers</th>
						</tr>
					</thead>
					<tbody>
						{#each raceResults.team_scores as t}
							<tr class:incomplete={!t.complete}>
								<td>{t.complete ? ordinal(t.place) : '—'}</td>
								<td class="team-name">{t.team}</td>
								<td>{t.complete ? t.score : `${t.runner_count} runner${t.runner_count === 1 ? '' : 's'}`}</td>
								<td class="mono-list">
									{#each t.scorers as s}
										<span class="place-chip" title={s.name}>{s.place}</span>
									{/each}
									{#if !t.complete}<span class="incomplete-note">incomplete team</span>{/if}
								</td>
								<td class="mono-list">
									{#each t.displacers as d}
										<span class="place-chip displacer" title={d.name}>{d.place}</span>
									{/each}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>

		<div class="panel">
			<h4>Individual Results</h4>
			{#if raceResults.individual_results.length === 0}
				<p class="muted">No finishers recorded yet.</p>
			{:else}
				<table>
					<thead>
						<tr>
							<th>Place</th>
							<th>Bib</th>
							<th>Name</th>
							<th>Team</th>
							<th>Time</th>
						</tr>
					</thead>
					<tbody>
						{#each raceResults.individual_results as r}
							<tr class:dnf={r.status !== 'finished'}>
								<td>{r.status === 'finished' ? r.place : '—'}</td>
								<td>{r.bib || '—'}</td>
								<td>
									{#if r.first_name}
										{r.first_name} {r.last_name}
									{:else}
										<span class="unknown">Unknown runner</span>
									{/if}
									{#if r.is_scorer}<span class="badge badge-accent tiny">Scorer</span>{/if}
									{#if r.is_displacer}<span class="badge tiny">Displacer</span>{/if}
									{#if r.status !== 'finished'}<span class="badge tiny status-badge">{r.status.toUpperCase()}</span>{/if}
								</td>
								<td>{r.team || '—'}</td>
								<td>{formatTime(r.time_seconds)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</div>
	</div>
</div>

<style>
	.race-results {
		margin-bottom: 36px;
	}
	.race-results-header {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 14px;
	}
	.race-link {
		margin-left: auto;
		font-size: 12.5px;
		color: var(--text-muted);
	}
	.race-link:hover {
		color: var(--accent);
		text-decoration: underline;
	}
	.results-grid {
		display: grid;
		grid-template-columns: 1.1fr 1fr;
		gap: 16px;
		align-items: start;
	}
	.panel {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 16px;
		overflow-x: auto;
	}
	.panel h4 {
		margin-bottom: 10px;
		font-size: 13px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}
	.muted {
		color: var(--text-muted);
		font-size: 13px;
	}
	.team-name {
		font-weight: 600;
	}
	tr.incomplete {
		opacity: 0.6;
	}
	tr.dnf {
		opacity: 0.55;
	}
	.mono-list {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}
	.place-chip {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 22px;
		height: 22px;
		padding: 0 5px;
		border-radius: 6px;
		background: var(--accent-soft);
		color: #4ade80;
		font-size: 12px;
		font-weight: 700;
	}
	.place-chip.displacer {
		background: var(--bg-elevated);
		color: var(--text-muted);
	}
	.incomplete-note {
		font-size: 11.5px;
		color: var(--text-faint);
		align-self: center;
	}
	.unknown {
		color: var(--text-faint);
		font-style: italic;
	}
	.tiny {
		margin-left: 6px;
		font-size: 10px;
		padding: 1px 6px;
	}
	.status-badge {
		color: var(--red);
		border-color: rgba(239, 68, 68, 0.4);
	}

	@media (max-width: 900px) {
		.results-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
