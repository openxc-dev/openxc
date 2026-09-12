<script>
	import { onDestroy } from 'svelte';
	import { api } from '../api';
	import { formatClock } from '../format';
	import StartRaceModal from './StartRaceModal.svelte';

	export let meetId;
	export let races = [];
	export let onChanged = () => {};

	let editingId = null;
	let draft = {};
	let creating = false;
	let newRace = { name: '', distance: '', scoring_athletes: 5, displacers: 2 };
	let error = '';
	let deletingRace = null;
	let startingRace = null;
	let resettingRace = null;

	let nowTick = Date.now();
	const tickInterval = setInterval(() => (nowTick = Date.now()), 1000);
	onDestroy(() => clearInterval(tickInterval));

	function raceStatus(race) {
		if (!race.start_time) return 'not_started';
		if (race.finish_time) return 'finished';
		return 'started';
	}

	function raceStatusLabel(status) {
		if (status === 'not_started') return 'Not Started';
		if (status === 'started') return 'Started';
		return 'Finished';
	}

	function raceElapsedSeconds(race, now) {
		if (!race.start_time) return 0;
		const start = new Date(race.start_time).getTime();
		const end = race.finish_time ? new Date(race.finish_time).getTime() : now;
		return (end - start) / 1000;
	}

	async function onStarted() {
		startingRace = null;
		await onChanged();
	}

	async function toggleFinish(race, checked) {
		error = '';
		try {
			await api.updateRace(race.id, { finish_time: checked ? new Date().toISOString() : null });
			await onChanged();
		} catch (e) {
			error = e.message;
		}
	}

	async function confirmReset() {
		if (!resettingRace) return;
		error = '';
		try {
			await api.updateRace(resettingRace.id, { start_time: null, finish_time: null });
			resettingRace = null;
			await onChanged();
		} catch (e) {
			error = e.message;
		}
	}

	function startEdit(race) {
		editingId = race.id;
		draft = { ...race };
	}

	function cancelEdit() {
		editingId = null;
	}

	async function saveEdit() {
		error = '';
		try {
			await api.updateRace(editingId, {
				name: draft.name,
				distance: draft.distance,
				scoring_athletes: Number(draft.scoring_athletes),
				displacers: Number(draft.displacers)
			});
			editingId = null;
			await onChanged();
		} catch (e) {
			error = e.message;
		}
	}

	async function createRace() {
		if (!newRace.name.trim()) {
			error = 'Race name is required';
			return;
		}
		error = '';
		try {
			await api.createRace(meetId, {
				...newRace,
				scoring_athletes: Number(newRace.scoring_athletes),
				displacers: Number(newRace.displacers)
			});
			newRace = { name: '', distance: '', scoring_athletes: 5, displacers: 2 };
			creating = false;
			await onChanged();
		} catch (e) {
			error = e.message;
		}
	}

	async function confirmDelete() {
		if (!deletingRace) return;
		await api.deleteRace(deletingRace.id);
		deletingRace = null;
		await onChanged();
	}

	// The `autofocus` HTML attribute doesn't reliably steal focus for a
	// form opened from a button click (or here, a keyboard shortcut right
	// after a click elsewhere) — Chromium's heuristic declines to move
	// focus away from whatever the user just interacted with. Focusing
	// imperatively on mount works regardless.
	function autofocus(node) {
		node.focus();
	}

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (deletingRace) {
				deletingRace = null;
			} else if (resettingRace) {
				resettingRace = null;
			}
			return;
		}
		if (e.altKey && e.key.toLowerCase() === 'n') {
			e.preventDefault();
			creating = true;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="header-row">
	<h2>Races</h2>
	<button class="btn btn-primary btn-sm" on:click={() => (creating = !creating)}>
		{creating ? 'Cancel' : '+ Add Race'}
	</button>
</div>

{#if error}<p class="error">{error}</p>{/if}

{#if creating}
	<div class="card new-race-form">
		<div class="grid">
			<div class="field">
				<label for="new-race-name">Race name</label>
				<input id="new-race-name" class="input" bind:value={newRace.name} placeholder="Boys Varsity" use:autofocus />
			</div>
			<div class="field">
				<label for="new-race-distance">Distance</label>
				<input id="new-race-distance" class="input" bind:value={newRace.distance} placeholder="5000m" />
			</div>
			<div class="field">
				<label for="new-race-scorers">Scoring athletes</label>
				<input id="new-race-scorers" class="input" type="number" min="1" bind:value={newRace.scoring_athletes} />
			</div>
			<div class="field">
				<label for="new-race-displacers">Displacers</label>
				<input id="new-race-displacers" class="input" type="number" min="0" bind:value={newRace.displacers} />
			</div>
		</div>
		<div class="actions">
			<button class="btn btn-primary" on:click={createRace}>Create Race</button>
		</div>
	</div>
{/if}

{#if races.length === 0 && !creating}
	<div class="empty-state">
		<p>No races yet. Add your first race to start assigning athletes.</p>
	</div>
{:else}
	<div class="race-grid">
		{#each races as race (race.id)}
			<div class="card race-card">
				{#if editingId === race.id}
					<div class="grid">
						<div class="field">
							<label for="edit-name-{race.id}">Race name</label>
							<input id="edit-name-{race.id}" class="input" bind:value={draft.name} />
						</div>
						<div class="field">
							<label for="edit-distance-{race.id}">Distance</label>
							<input id="edit-distance-{race.id}" class="input" bind:value={draft.distance} />
						</div>
						<div class="field">
							<label for="edit-scorers-{race.id}">Scoring athletes</label>
							<input id="edit-scorers-{race.id}" class="input" type="number" min="1" bind:value={draft.scoring_athletes} />
						</div>
						<div class="field">
							<label for="edit-displacers-{race.id}">Displacers</label>
							<input id="edit-displacers-{race.id}" class="input" type="number" min="0" bind:value={draft.displacers} />
						</div>
					</div>
					<div class="actions">
						<button class="btn btn-sm" on:click={cancelEdit}>Cancel</button>
						<button class="btn btn-primary btn-sm" on:click={saveEdit}>Save</button>
					</div>
				{:else}
					<div class="race-card-header">
						<h3>{race.name}</h3>
						<div class="race-card-actions">
							<button class="btn btn-sm" on:click={() => startEdit(race)}>Edit</button>
							<button class="btn btn-sm btn-danger" on:click={() => (deletingRace = race)}>Delete</button>
						</div>
					</div>
					<div class="race-meta">
						{#if race.distance}<span class="badge">{race.distance}</span>{/if}
						<span class="badge">{race.athlete_count} athletes</span>
						<span class="badge">{race.finisher_count} finishers</span>
					</div>
					<div class="timing-row">
						<div class="timing-status">
							<span class="status-badge status-{raceStatus(race)}">{raceStatusLabel(raceStatus(race))}</span>
							<span class="elapsed-clock">{formatClock(raceElapsedSeconds(race, nowTick))}</span>
						</div>
						{#if raceStatus(race) === 'not_started'}
							<button class="btn btn-sm" on:click={() => (startingRace = race)}>Start</button>
						{:else}
							<div class="timing-actions">
								<label class="finish-toggle">
									<input
										type="checkbox"
										checked={raceStatus(race) === 'finished'}
										on:change={(e) => toggleFinish(race, e.target.checked)}
									/>
									<span class="toggle-track"><span class="toggle-thumb"></span></span>
									Finish
								</label>
								<button class="btn btn-sm" on:click={() => (resettingRace = race)}>Reset</button>
							</div>
						{/if}
					</div>
					<div class="scoring-config">
						<div class="scoring-item">
							<span class="scoring-value">{race.scoring_athletes}</span>
							<span class="scoring-label">scorers</span>
						</div>
						<div class="scoring-item">
							<span class="scoring-value">{race.displacers}</span>
							<span class="scoring-label">displacers</span>
						</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

{#if deletingRace}
	<div class="overlay" on:click={() => (deletingRace = null)} role="presentation">
		<div class="confirm card" on:click|stopPropagation role="dialog" aria-modal="true">
			<h3>Delete "{deletingRace.name}"?</h3>
			<p class="confirm-text">
				This removes the race and all its finish results. Athletes assigned to it will become unassigned.
			</p>
			<div class="actions">
				<button class="btn" on:click={() => (deletingRace = null)}>Cancel</button>
				<button class="btn btn-danger" on:click={confirmDelete}>Delete Race</button>
			</div>
		</div>
	</div>
{/if}

{#if startingRace}
	<StartRaceModal {meetId} race={startingRace} onClose={() => (startingRace = null)} {onStarted} />
{/if}

{#if resettingRace}
	<div class="overlay" on:click={() => (resettingRace = null)} role="presentation">
		<div class="confirm card" on:click|stopPropagation role="dialog" aria-modal="true">
			<h3>Reset "{resettingRace.name}" to not started?</h3>
			<p class="confirm-text">
				This clears its start and finish time so you can start it again — useful if the start time
				needs to be corrected. Finish results already recorded for this race are not affected.
			</p>
			<div class="actions">
				<button class="btn" on:click={() => (resettingRace = null)}>Cancel</button>
				<button class="btn btn-danger" on:click={confirmReset}>Reset Race</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 16px;
	}

	.error {
		color: var(--red);
		font-size: 13px;
	}

	.new-race-form {
		padding: 18px;
		margin-bottom: 18px;
	}

	.grid {
		display: grid;
		grid-template-columns: 2fr 1fr 1fr 1fr;
		gap: 12px;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 14px;
	}

	.race-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 14px;
	}

	.race-card {
		padding: 16px;
	}

	.race-card-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.race-card-actions {
		display: flex;
		gap: 6px;
	}

	.race-meta {
		display: flex;
		gap: 6px;
		margin-top: 10px;
		flex-wrap: wrap;
	}

	.timing-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		margin-top: 14px;
		padding-top: 14px;
		border-top: 1px solid var(--border);
	}

	.timing-status {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.timing-actions {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.elapsed-clock {
		font-variant-numeric: tabular-nums;
		font-size: 18px;
		font-weight: 700;
	}

	.status-badge {
		display: inline-flex;
		align-items: center;
		padding: 3px 9px;
		border-radius: 999px;
		font-size: 10.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		border: 1px solid var(--border);
	}

	.status-not_started {
		background: var(--bg-elevated);
		color: var(--text-faint);
	}

	.status-started {
		background: rgba(34, 197, 94, 0.15);
		border-color: rgba(34, 197, 94, 0.4);
		color: var(--accent-text);
	}

	.status-finished {
		background: rgba(59, 130, 246, 0.15);
		border-color: rgba(59, 130, 246, 0.4);
		color: var(--blue);
	}

	.finish-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		cursor: pointer;
		font-size: 12.5px;
		color: var(--text-muted);
		font-weight: 500;
		user-select: none;
	}

	.finish-toggle input {
		position: absolute;
		opacity: 0;
		width: 0;
		height: 0;
	}

	.toggle-track {
		position: relative;
		width: 34px;
		height: 20px;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 999px;
		flex-shrink: 0;
		transition: background 0.15s, border-color 0.15s;
	}

	.toggle-thumb {
		position: absolute;
		top: 1px;
		left: 1px;
		width: 16px;
		height: 16px;
		border-radius: 50%;
		background: var(--text-faint);
		transition: transform 0.15s, background 0.15s;
	}

	.finish-toggle input:checked + .toggle-track {
		background: var(--accent-soft);
		border-color: var(--accent);
	}

	.finish-toggle input:checked + .toggle-track .toggle-thumb {
		transform: translateX(14px);
		background: var(--accent);
	}

	.scoring-config {
		display: flex;
		gap: 20px;
		margin-top: 16px;
		padding-top: 14px;
		border-top: 1px solid var(--border);
	}

	.scoring-item {
		display: flex;
		flex-direction: column;
	}

	.scoring-value {
		font-size: 22px;
		font-weight: 700;
		color: var(--accent);
	}

	.scoring-label {
		font-size: 11px;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.55);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
		padding: 20px;
	}

	.confirm {
		padding: 20px;
		width: 100%;
		max-width: 420px;
	}

	.confirm-text {
		color: var(--text-muted);
		font-size: 13.5px;
		margin: 8px 0 18px;
	}

	@media (max-width: 640px) {
		.grid {
			grid-template-columns: 1fr 1fr;
		}
	}
</style>
