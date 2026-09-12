<script>
	import { onDestroy, onMount, tick } from 'svelte';
	import { api } from '../api';
	import { formatTime, formatClock } from '../format';
	import FinisherEditModal from './FinisherEditModal.svelte';

	export let meetId;
	export let races = [];

	let finishes = [];
	let loading = true;
	let error = '';
	let hint = '';

	let bibInput = '';
	let bibInputEl;
	let listEl;

	let manualBib = '';
	let manualRaceId = '';

	let editingFinisher = null;

	$: raceById = Object.fromEntries(races.map((r) => [r.id, r]));

	// The clock shows real elapsed time for whichever race(s) are currently
	// started-and-not-finished, driven by each race's own start_time —
	// there's no operator-run stopwatch anymore, so nothing to forget to
	// start/stop, and it stays correct even if multiple races overlap.
	let nowTick = Date.now();
	const clockInterval = setInterval(() => (nowTick = Date.now()), 1000);
	onDestroy(() => clearInterval(clockInterval));

	$: activeRaces = races
		.filter((r) => r.start_time && !r.finish_time)
		.slice()
		.sort((a, b) => new Date(a.start_time) - new Date(b.start_time));

	function raceElapsedSeconds(race, now) {
		return (now - new Date(race.start_time).getTime()) / 1000;
	}

	$: clockDisplay =
		activeRaces.length === 0
			? 'No active race'
			: activeRaces.map((r) => formatClock(raceElapsedSeconds(r, nowTick))).join(' / ');

	async function load() {
		loading = true;
		error = '';
		try {
			finishes = await api.listFinishes(meetId);
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(load);

	async function scrollToBottom() {
		await tick();
		if (listEl) listEl.scrollTop = listEl.scrollHeight;
	}

	async function pushFinish(data) {
		error = '';
		hint = '';
		const tempId = `temp-${Math.random().toString(36).slice(2)}`;
		const temp = {
			id: tempId,
			place: null,
			bib: data.bib,
			time_seconds: data.time_seconds,
			status: 'finished',
			is_unknown: !data.bib,
			notes: null,
			athlete: null,
			race: data.race_id ? raceById[data.race_id] : null,
			pending: true
		};
		finishes = [...finishes, temp];
		scrollToBottom();
		try {
			const real = await api.recordFinish(meetId, data);
			finishes = finishes.map((f) => (f.id === tempId ? real : f));
			return true;
		} catch (e) {
			finishes = finishes.filter((f) => f.id !== tempId);
			error = e.message;
			return false;
		}
	}

	async function recordBib() {
		const bib = bibInput.trim();
		if (!bib) return;
		bibInput = '';
		// time_seconds is omitted — the backend derives it from the resolved
		// race's real start_time, since which race a scanned bib belongs to
		// isn't known here yet.
		const ok = await pushFinish({ bib });
		if (!ok) {
			// Couldn't auto-resolve a race for this bib — hand it to the
			// manual panel below so the operator can pick the race in one step.
			manualBib = bib;
			hint = `Bib ${bib} needs a race picked below.`;
		}
		bibInputEl?.focus();
	}

	async function recordManual() {
		if (!manualRaceId) {
			error = 'Pick a race first.';
			return;
		}
		const bib = manualBib.trim();
		manualBib = '';
		await pushFinish({ bib: bib || null, race_id: manualRaceId });
	}

	async function undoLast() {
		const last = finishes[finishes.length - 1];
		if (!last || last.pending) return;
		finishes = finishes.slice(0, -1);
		try {
			await api.deleteFinisher(last.id);
		} catch (e) {
			error = e.message;
			await load();
		}
	}

	async function removeFinish(finish) {
		finishes = finishes.filter((f) => f.id !== finish.id);
		try {
			await api.deleteFinisher(finish.id);
		} catch (e) {
			error = e.message;
			await load();
		}
	}

	function athleteLabel(f) {
		if (f.athlete) return `${f.athlete.first_name} ${f.athlete.last_name}`;
		if (f.bib) return 'Unmatched bib';
		return 'Unknown runner';
	}

	async function onSavedCorrection() {
		editingFinisher = null;
		await load();
	}
</script>

<div class="entry-layout">
	<div class="entry-controls card">
		<div class="clock-row">
			<span class="clock-display">{clockDisplay}</span>
		</div>

		{#if races.length === 0}
			<p class="muted">Create a race first in the Races tab.</p>
		{:else}
			<form class="bib-form" on:submit|preventDefault={recordBib}>
				<input
					class="input bib-input"
					placeholder="Scan or type bib #, then Enter"
					bind:value={bibInput}
					bind:this={bibInputEl}
					inputmode="numeric"
					autofocus
				/>
				<button type="submit" class="btn btn-primary">Record</button>
			</form>
			<p class="bib-hint">The race is detected automatically from the athlete's roster entry.</p>

			<button class="btn btn-sm undo-btn" on:click={undoLast} disabled={finishes.length === 0}>Undo Last</button>

			<div class="manual-panel">
				<h4>Unmatched or no-bib finisher</h4>
				<p class="muted manual-hint">
					Used when a bib doesn't match anyone on the roster, or you didn't catch it — pick which
					race it belongs to.
				</p>
				<div class="manual-row">
					<input class="input" placeholder="Bib (optional)" bind:value={manualBib} inputmode="numeric" />
					<select class="select" bind:value={manualRaceId}>
						<option value="">Select race…</option>
						{#each races as race}
							<option value={race.id}>{race.name}</option>
						{/each}
					</select>
				</div>
				<button class="btn btn-sm" on:click={recordManual}>Record</button>
			</div>
		{/if}

		{#if hint}<p class="hint">{hint}</p>{/if}
		{#if error}<p class="error">{error}</p>{/if}
	</div>

	<div class="finish-feed card">
		<div class="feed-header">
			<h3>Recent Finishes</h3>
			<span class="muted">{finishes.length} recorded</span>
		</div>
		<div class="feed-list scrollbar-thin" bind:this={listEl}>
			{#if loading}
				<p class="muted feed-empty">Loading…</p>
			{:else if finishes.length === 0}
				<p class="muted feed-empty">No finishes recorded yet.</p>
			{:else}
				{#each finishes as f (f.id)}
					<div class="feed-row" class:pending={f.pending} class:dnf={f.status !== 'finished'}>
						<div class="feed-place">{f.pending ? '…' : f.place}</div>
						<div class="feed-main">
							<div class="feed-name">
								{athleteLabel(f)}
								{#if f.race}<span class="badge badge-accent">{f.race.name}</span>{/if}
								{#if f.status !== 'finished'}<span class="badge feed-status">{f.status.toUpperCase()}</span>{/if}
							</div>
							<div class="feed-sub">
								{#if f.bib}Bib {f.bib}{:else}No bib{/if}
								{#if f.athlete?.team}&nbsp;·&nbsp;{f.athlete.team.name}{/if}
								{#if f.time_seconds != null}&nbsp;·&nbsp;{formatTime(f.time_seconds)}{/if}
							</div>
						</div>
						{#if !f.pending}
							<div class="feed-actions">
								<button class="icon-btn" title="Edit" on:click={() => (editingFinisher = f)}>✎</button>
								<button class="icon-btn danger" title="Delete" on:click={() => removeFinish(f)}>🗑</button>
							</div>
						{/if}
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>

{#if editingFinisher}
	<FinisherEditModal finisher={editingFinisher} onClose={() => (editingFinisher = null)} onSaved={onSavedCorrection} />
{/if}

<style>
	.entry-layout {
		display: grid;
		grid-template-columns: 340px 1fr;
		gap: 18px;
		align-items: start;
		height: 100%;
	}

	.entry-controls {
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		position: sticky;
		top: 20px;
	}

	.clock-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.clock-display {
		font-variant-numeric: tabular-nums;
		font-size: 22px;
		font-weight: 700;
		flex: 1;
	}

	.bib-form {
		display: flex;
		gap: 8px;
	}

	.bib-input {
		font-size: 18px;
		padding: 12px;
		text-align: center;
	}

	.bib-hint {
		font-size: 11.5px;
		color: var(--text-faint);
		margin: -6px 0 0;
	}

	.undo-btn {
		align-self: flex-start;
	}

	.manual-panel {
		border-top: 1px solid var(--border);
		padding-top: 14px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.manual-panel h4 {
		font-size: 12px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-muted);
	}

	.manual-hint {
		font-size: 11.5px;
		margin: 0;
		line-height: 1.5;
	}

	.manual-row {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.hint {
		color: var(--amber);
		font-size: 12.5px;
		margin: 0;
	}

	.error {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}

	.muted {
		color: var(--text-muted);
		font-size: 13px;
	}

	.finish-feed {
		display: flex;
		flex-direction: column;
		min-height: 500px;
		max-height: calc(100vh - 120px);
	}

	.feed-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 16px;
		border-bottom: 1px solid var(--border);
	}

	.feed-list {
		overflow-y: auto;
		flex: 1;
	}

	.feed-empty {
		padding: 30px;
		text-align: center;
	}

	.feed-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 16px;
		border-bottom: 1px solid var(--border);
	}

	.feed-row:hover {
		background: var(--bg-hover);
	}

	.feed-row.pending {
		opacity: 0.55;
	}

	.feed-row.dnf {
		background: rgba(239, 68, 68, 0.06);
	}

	.feed-place {
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

	.feed-main {
		flex: 1;
		min-width: 0;
	}

	.feed-name {
		font-weight: 600;
		font-size: 13.5px;
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}

	.feed-status {
		color: var(--red);
		border-color: rgba(239, 68, 68, 0.4);
	}

	.feed-sub {
		font-size: 12px;
		color: var(--text-muted);
		margin-top: 2px;
	}

	.feed-actions {
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

	.icon-btn.danger:hover {
		color: #fca5a5;
	}

	@media (max-width: 900px) {
		.entry-layout {
			grid-template-columns: 1fr;
		}
		.entry-controls {
			position: static;
		}
	}
</style>
