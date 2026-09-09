<script>
	import { onMount } from 'svelte';
	import { api } from '../api';
	import ResultsView from './ResultsView.svelte';

	export let meetId;

	let results = null;
	let loading = true;
	let error = '';

	async function load() {
		loading = true;
		error = '';
		try {
			results = await api.getMeetResults(meetId);
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<div class="header-row">
	<h2>Results</h2>
	<div class="header-actions">
		<button class="btn btn-sm" on:click={load}>Refresh</button>
		<a class="btn btn-sm" href="/results/{meetId}" target="_blank" rel="noreferrer">Open Public Page ↗</a>
	</div>
</div>

{#if loading}
	<p class="muted">Loading results…</p>
{:else if error}
	<p class="error">{error}</p>
{:else if results.races.length === 0}
	<div class="empty-state"><p>No races yet.</p></div>
{:else}
	{#each results.races as raceResults (raceResults.race.id)}
		<ResultsView {raceResults} showRaceLink />
	{/each}
{/if}

<style>
	.header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 16px;
	}
	.header-actions {
		display: flex;
		gap: 8px;
	}
	.muted {
		color: var(--text-muted);
	}
	.error {
		color: var(--red);
	}
</style>
