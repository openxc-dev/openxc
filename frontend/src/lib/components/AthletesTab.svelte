<script>
	import { onMount } from 'svelte';
	import { api } from '../api';
	import AthleteFormModal from './AthleteFormModal.svelte';
	import BulkImportModal from './BulkImportModal.svelte';

	export let meetId;
	export let races = [];
	export let teams = [];

	let athletes = [];
	let loading = true;
	let error = '';

	let search = '';
	let raceFilter = '';
	let teamFilter = '';
	let sortKey = 'bib';
	let sortDir = 1;

	let showForm = false;
	let editingAthlete = null;
	let showBulk = false;
	let deletingAthlete = null;
	let editingRaceForId = null;

	let selectedIds = new Set();
	let bulkTeamId = '';
	let bulkRaceId = '';
	let bulkSaving = false;

	$: raceById = Object.fromEntries(races.map((r) => [r.id, r]));
	$: teamById = Object.fromEntries(teams.map((t) => [t.id, t]));

	async function load() {
		loading = true;
		error = '';
		try {
			athletes = await api.listAthletes(meetId);
			const validIds = new Set(athletes.map((a) => a.id));
			selectedIds = new Set([...selectedIds].filter((id) => validIds.has(id)));
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(load);

	$: filtered = athletes
		.filter((a) => (raceFilter ? a.race_id === raceFilter : true))
		.filter((a) => (teamFilter ? a.team_id === teamFilter : true))
		.filter((a) => {
			if (!search.trim()) return true;
			const q = search.toLowerCase();
			return (
				a.bib.toLowerCase().includes(q) ||
				a.first_name.toLowerCase().includes(q) ||
				a.last_name.toLowerCase().includes(q) ||
				(teamById[a.team_id]?.name || '').toLowerCase().includes(q)
			);
		})
		.slice()
		.sort((a, b) => {
			let av, bv;
			if (sortKey === 'race') {
				av = raceById[a.race_id]?.name || '';
				bv = raceById[b.race_id]?.name || '';
			} else if (sortKey === 'team') {
				av = teamById[a.team_id]?.name || '';
				bv = teamById[b.team_id]?.name || '';
			} else {
				av = a[sortKey] || '';
				bv = b[sortKey] || '';
			}
			if (sortKey === 'bib') {
				const an = Number(av);
				const bn = Number(bv);
				if (!isNaN(an) && !isNaN(bn)) return (an - bn) * sortDir;
			}
			return String(av).localeCompare(String(bv)) * sortDir;
		});

	$: allFilteredSelected = filtered.length > 0 && filtered.every((a) => selectedIds.has(a.id));
	$: someFilteredSelected = filtered.some((a) => selectedIds.has(a.id));

	function toggleSelect(athlete) {
		const next = new Set(selectedIds);
		if (next.has(athlete.id)) {
			next.delete(athlete.id);
		} else {
			next.add(athlete.id);
		}
		selectedIds = next;
	}

	function toggleSelectAll() {
		const next = new Set(selectedIds);
		if (allFilteredSelected) {
			filtered.forEach((a) => next.delete(a.id));
		} else {
			filtered.forEach((a) => next.add(a.id));
		}
		selectedIds = next;
	}

	function clearSelection() {
		selectedIds = new Set();
		bulkTeamId = '';
		bulkRaceId = '';
	}

	async function applyBulkTeam() {
		if (!bulkTeamId || selectedIds.size === 0) return;
		bulkSaving = true;
		error = '';
		try {
			await api.bulkUpdateAthleteTeam(meetId, Array.from(selectedIds), bulkTeamId);
			clearSelection();
			await load();
		} catch (e) {
			error = e.message;
		} finally {
			bulkSaving = false;
		}
	}

	async function applyBulkRace() {
		if (!bulkRaceId || selectedIds.size === 0) return;
		bulkSaving = true;
		error = '';
		try {
			await api.bulkUpdateAthleteRace(meetId, Array.from(selectedIds), bulkRaceId);
			clearSelection();
			await load();
		} catch (e) {
			error = e.message;
		} finally {
			bulkSaving = false;
		}
	}

	function indeterminate(node, value) {
		node.indeterminate = value;
		return {
			update(v) {
				node.indeterminate = v;
			}
		};
	}

	function sortBy(key) {
		if (sortKey === key) {
			sortDir *= -1;
		} else {
			sortKey = key;
			sortDir = 1;
		}
	}

	function openCreate() {
		editingAthlete = null;
		showForm = true;
	}

	function openEdit(athlete) {
		editingAthlete = athlete;
		showForm = true;
	}

	async function onSaved() {
		showForm = false;
		showBulk = false;
		await load();
	}

	async function confirmDelete() {
		if (!deletingAthlete) return;
		await api.deleteAthlete(deletingAthlete.id);
		deletingAthlete = null;
		await load();
	}

	function startEditRace(athlete) {
		editingRaceForId = athlete.id;
	}

	async function changeRace(athlete, newRaceId) {
		editingRaceForId = null;
		const value = newRaceId || null;
		if (value === athlete.race_id) return;

		const prevRaceId = athlete.race_id;
		athletes = athletes.map((a) => (a.id === athlete.id ? { ...a, race_id: value } : a));
		try {
			await api.updateAthlete(athlete.id, { race_id: value });
		} catch (e) {
			error = e.message;
			athletes = athletes.map((a) => (a.id === athlete.id ? { ...a, race_id: prevRaceId } : a));
		}
	}

	function focusAndOpen(node) {
		node.focus();
		if (typeof node.showPicker === 'function') {
			try {
				node.showPicker();
			} catch {
				// ignore — not supported in this browser context
			}
		}
	}

	function handleKeydown(e) {
		if (e.key === 'Escape' && deletingAthlete) {
			deletingAthlete = null;
			return;
		}
		if (e.altKey && e.key.toLowerCase() === 'n') {
			e.preventDefault();
			openCreate();
		} else if (e.altKey && e.key.toLowerCase() === 'b') {
			e.preventDefault();
			showBulk = true;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="header-row">
	<h2>Athletes <span class="count">({athletes.length})</span></h2>
	<div class="header-actions">
		<button class="btn btn-sm" on:click={() => (showBulk = true)}>Bulk Import</button>
		<button class="btn btn-primary btn-sm" on:click={openCreate}>+ Add Athlete</button>
	</div>
</div>

<div class="filters">
	<input class="input search" placeholder="Search name, bib, team…" bind:value={search} />
	<select class="select race-filter" bind:value={raceFilter}>
		<option value="">All races</option>
		{#each races as race}
			<option value={race.id}>{race.name}</option>
		{/each}
	</select>
	<select class="select race-filter" bind:value={teamFilter}>
		<option value="">All teams</option>
		{#each teams as team}
			<option value={team.id}>{team.name}</option>
		{/each}
	</select>
</div>

{#if selectedIds.size > 0}
	<div class="bulk-bar card">
		<span class="bulk-count">{selectedIds.size} selected</span>
		<div class="bulk-group">
			<select class="select bulk-select" bind:value={bulkTeamId}>
				<option value="">Choose team…</option>
				{#each teams as team}
					<option value={team.id}>{team.name}</option>
				{/each}
			</select>
			<button class="btn btn-primary btn-sm" on:click={applyBulkTeam} disabled={bulkSaving || !bulkTeamId}>
				{bulkSaving ? 'Applying…' : 'Change Team'}
			</button>
		</div>
		<div class="bulk-group">
			<select class="select bulk-select" bind:value={bulkRaceId}>
				<option value="">Choose race…</option>
				{#each races as race}
					<option value={race.id}>{race.name}</option>
				{/each}
			</select>
			<button class="btn btn-primary btn-sm" on:click={applyBulkRace} disabled={bulkSaving || !bulkRaceId}>
				{bulkSaving ? 'Applying…' : 'Change Race'}
			</button>
		</div>
		<button class="btn btn-sm" on:click={clearSelection}>Cancel</button>
	</div>
{/if}

{#if error}
	<p class="error">{error}</p>
{:else if loading}
	<p class="muted">Loading athletes…</p>
{:else if athletes.length === 0}
	<div class="empty-state">
		<p>No athletes yet. Add one or use bulk import to load a roster quickly.</p>
	</div>
{:else}
	<div class="table-wrap card scrollbar-thin">
		<table>
			<thead>
				<tr>
					<th class="checkbox-cell">
						<input
							type="checkbox"
							checked={allFilteredSelected}
							use:indeterminate={someFilteredSelected && !allFilteredSelected}
							on:change={toggleSelectAll}
							aria-label="Select all"
						/>
					</th>
					<th on:click={() => sortBy('bib')}>Bib {sortKey === 'bib' ? (sortDir > 0 ? '↑' : '↓') : ''}</th>
					<th on:click={() => sortBy('last_name')}>Name {sortKey === 'last_name' ? (sortDir > 0 ? '↑' : '↓') : ''}</th>
					<th on:click={() => sortBy('team')}>Team {sortKey === 'team' ? (sortDir > 0 ? '↑' : '↓') : ''}</th>
					<th on:click={() => sortBy('grade')}>Grade {sortKey === 'grade' ? (sortDir > 0 ? '↑' : '↓') : ''}</th>
					<th on:click={() => sortBy('race')}>Race {sortKey === 'race' ? (sortDir > 0 ? '↑' : '↓') : ''}</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each filtered as athlete (athlete.id)}
					<tr class:selected-row={selectedIds.has(athlete.id)}>
						<td class="checkbox-cell">
							<input
								type="checkbox"
								checked={selectedIds.has(athlete.id)}
								on:change={() => toggleSelect(athlete)}
								aria-label="Select {athlete.first_name} {athlete.last_name}"
							/>
						</td>
						<td>{athlete.bib}</td>
						<td>{athlete.first_name} {athlete.last_name}</td>
						<td>{teamById[athlete.team_id]?.name || '—'}</td>
						<td>{athlete.grade || '—'}</td>
						<td>
							{#if editingRaceForId === athlete.id}
								<select
									class="select race-edit-select"
									value={athlete.race_id || ''}
									use:focusAndOpen
									on:change={(e) => changeRace(athlete, e.target.value)}
									on:blur={() => (editingRaceForId = null)}
									on:keydown={(e) => e.key === 'Escape' && (editingRaceForId = null)}
								>
									<option value="">Unassigned</option>
									{#each races as race}
										<option value={race.id}>{race.name}</option>
									{/each}
								</select>
							{:else if raceById[athlete.race_id]}
								<span
									class="badge badge-accent badge-clickable"
									role="button"
									tabindex="0"
									on:click={() => startEditRace(athlete)}
									on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && startEditRace(athlete)}
								>
									{raceById[athlete.race_id].name}
								</span>
							{:else}
								<span
									class="badge badge-clickable"
									role="button"
									tabindex="0"
									on:click={() => startEditRace(athlete)}
									on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && startEditRace(athlete)}
								>
									Unassigned
								</span>
							{/if}
						</td>
						<td class="actions-cell">
							<button class="btn btn-sm" on:click={() => openEdit(athlete)}>Edit</button>
							<button class="btn btn-sm btn-danger" on:click={() => (deletingAthlete = athlete)}>Delete</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#if filtered.length === 0}
			<p class="muted no-results">No athletes match your filters.</p>
		{/if}
	</div>
{/if}

{#if showForm}
	<AthleteFormModal {meetId} {races} {teams} athlete={editingAthlete} onClose={() => (showForm = false)} {onSaved} />
{/if}

{#if showBulk}
	<BulkImportModal {meetId} {races} {teams} onClose={() => (showBulk = false)} {onSaved} />
{/if}

{#if deletingAthlete}
	<div class="overlay" on:click={() => (deletingAthlete = null)} role="presentation">
		<div class="confirm card" on:click|stopPropagation role="dialog" aria-modal="true">
			<h3>Remove {deletingAthlete.first_name} {deletingAthlete.last_name}?</h3>
			<p class="confirm-text">This also removes any recorded finish results for this athlete.</p>
			<div class="actions">
				<button class="btn" on:click={() => (deletingAthlete = null)}>Cancel</button>
				<button class="btn btn-danger" on:click={confirmDelete}>Remove</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 14px;
	}
	.count {
		color: var(--text-muted);
		font-weight: 400;
	}
	.header-actions {
		display: flex;
		gap: 8px;
	}
	.filters {
		display: flex;
		gap: 10px;
		margin-bottom: 14px;
	}
	.bulk-bar {
		display: flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
		padding: 10px 14px;
		margin-bottom: 14px;
		border-color: var(--accent);
	}
	.bulk-count {
		font-size: 13px;
		font-weight: 600;
		color: var(--accent);
		white-space: nowrap;
	}
	.bulk-group {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.bulk-select {
		max-width: 200px;
	}
	.checkbox-cell {
		width: 32px;
		cursor: default;
	}
	.checkbox-cell input {
		cursor: pointer;
	}
	tr.selected-row {
		background: var(--accent-soft);
	}
	.search {
		max-width: 320px;
	}
	.race-filter {
		max-width: 220px;
	}
	.error {
		color: var(--red);
	}
	.muted {
		color: var(--text-muted);
	}
	.table-wrap {
		overflow-x: auto;
	}
	.badge-clickable {
		cursor: pointer;
	}
	.badge-clickable:hover {
		border-color: var(--accent);
	}
	.race-edit-select {
		width: auto;
		min-width: 140px;
		padding: 4px 8px;
		font-size: 12.5px;
	}
	.actions-cell {
		display: flex;
		gap: 6px;
	}
	.no-results {
		padding: 16px;
		text-align: center;
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
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}
</style>
