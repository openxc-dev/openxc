<script>
	import { api } from '../api';
	import { formatTime } from '../format';
	import FinisherEditModal from './FinisherEditModal.svelte';

	export let races = [];

	let raceId = '';
	let finishers = [];
	let loading = false;
	let error = '';
	let editingFinisher = null;

	$: if (races.length > 0 && !races.some((r) => r.id === raceId)) {
		raceId = races[0].id;
	}
	$: if (raceId) loadFinishers(raceId);

	async function loadFinishers(id) {
		loading = true;
		error = '';
		try {
			finishers = await api.listFinishers(id);
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function removeFinisher(finisher) {
		finishers = finishers.filter((f) => f.id !== finisher.id);
		try {
			await api.deleteFinisher(finisher.id);
		} catch (e) {
			error = e.message;
			await loadFinishers(raceId);
		}
	}

	async function move(finisher, dir) {
		const idx = finishers.findIndex((f) => f.id === finisher.id);
		const targetIdx = idx + dir;
		if (targetIdx < 0 || targetIdx >= finishers.length) return;
		const reordered = finishers.slice();
		[reordered[idx], reordered[targetIdx]] = [reordered[targetIdx], reordered[idx]];
		finishers = reordered;
		try {
			finishers = await api.reorderFinishers(
				raceId,
				reordered.map((f) => f.id)
			);
		} catch (e) {
			error = e.message;
			await loadFinishers(raceId);
		}
	}

	function athleteLabel(f) {
		if (f.athlete) return `${f.athlete.first_name} ${f.athlete.last_name}`;
		if (f.bib) return 'Unmatched bib';
		return 'Unknown runner';
	}

	async function onSavedCorrection() {
		editingFinisher = null;
		await loadFinishers(raceId);
	}
</script>

<div class="header-row">
	<h2>Finish Order</h2>
	<select class="select race-select" bind:value={raceId}>
		{#each races as race}
			<option value={race.id}>{race.name}</option>
		{/each}
	</select>
</div>

{#if races.length === 0}
	<div class="empty-state">
		<p>Create a race first in the Races tab.</p>
	</div>
{:else if error}
	<p class="error">{error}</p>
{/if}

{#if races.length > 0}
	<div class="finisher-list card">
		<div class="list-header">
			<span class="muted">{finishers.length} recorded</span>
		</div>
		<div class="list-body scrollbar-thin">
			{#if loading}
				<p class="muted list-empty">Loading…</p>
			{:else if finishers.length === 0}
				<p class="muted list-empty">
					No finishers recorded yet for this race. Record finishes on the Time Entry tab.
				</p>
			{:else}
				{#each finishers as f, i (f.id)}
					<div class="list-row" class:dnf={f.status !== 'finished'}>
						<div class="list-place">{f.place}</div>
						<div class="list-main">
							<div class="list-name">
								{athleteLabel(f)}
								{#if f.status !== 'finished'}<span class="badge list-status">{f.status.toUpperCase()}</span>{/if}
							</div>
							<div class="list-sub">
								{#if f.bib}Bib {f.bib}{:else}No bib{/if}
								{#if f.athlete?.team}&nbsp;·&nbsp;{f.athlete.team.name}{/if}
								{#if f.time_seconds != null}&nbsp;·&nbsp;{formatTime(f.time_seconds)}{/if}
							</div>
						</div>
						<div class="list-actions">
							<button class="icon-btn" title="Move up" on:click={() => move(f, -1)} disabled={i === 0}>↑</button>
							<button
								class="icon-btn"
								title="Move down"
								on:click={() => move(f, 1)}
								disabled={i === finishers.length - 1}>↓</button
							>
							<button class="icon-btn" title="Edit" on:click={() => (editingFinisher = f)}>✎</button>
							<button class="icon-btn danger" title="Delete" on:click={() => removeFinisher(f)}>🗑</button>
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
{/if}

{#if editingFinisher}
	<FinisherEditModal finisher={editingFinisher} onClose={() => (editingFinisher = null)} onSaved={onSavedCorrection} />
{/if}

<style>
	.header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 16px;
	}
	.race-select {
		max-width: 260px;
	}
	.error {
		color: var(--red);
		font-size: 13px;
	}
	.muted {
		color: var(--text-muted);
		font-size: 13px;
	}
	.finisher-list {
		display: flex;
		flex-direction: column;
		max-height: calc(100vh - 220px);
	}
	.list-header {
		padding: 12px 16px;
		border-bottom: 1px solid var(--border);
	}
	.list-body {
		overflow-y: auto;
		flex: 1;
	}
	.list-empty {
		padding: 30px;
		text-align: center;
	}
	.list-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 16px;
		border-bottom: 1px solid var(--border);
	}
	.list-row:hover {
		background: var(--bg-hover);
	}
	.list-row.dnf {
		background: rgba(239, 68, 68, 0.06);
	}
	.list-place {
		width: 34px;
		height: 34px;
		border-radius: 50%;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 13px;
		flex-shrink: 0;
	}
	.list-main {
		flex: 1;
		min-width: 0;
	}
	.list-name {
		font-weight: 600;
		font-size: 13.5px;
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.list-status {
		color: var(--red);
		border-color: rgba(239, 68, 68, 0.4);
	}
	.list-sub {
		font-size: 12px;
		color: var(--text-muted);
		margin-top: 2px;
	}
	.list-actions {
		display: flex;
		gap: 2px;
		flex-shrink: 0;
	}
	.icon-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		padding: 5px 7px;
		border-radius: 6px;
		font-size: 12px;
	}
	.icon-btn:hover {
		background: var(--bg-card);
		color: var(--text);
	}
	.icon-btn:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}
	.icon-btn.danger:hover {
		color: #fca5a5;
	}
</style>
