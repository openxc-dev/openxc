<script>
	import { page } from '$app/stores';
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';
	import { formatDate } from '$lib/format';
	import ResultsView from '$lib/components/ResultsView.svelte';

	$: meetId = $page.params.id;

	let results = null;
	let loading = true;
	let error = '';
	let refreshTimer;

	async function load() {
		error = '';
		try {
			results = await api.getMeetResults(meetId);
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		load();
		refreshTimer = setInterval(load, 15000);
	});

	onDestroy(() => clearInterval(refreshTimer));
</script>

<svelte:head>
	<title>{results ? `${results.meet.name} — Results` : 'Meet Results'}</title>
</svelte:head>

<div class="public-page">
	{#if loading}
		<div class="empty-state">Loading results…</div>
	{:else if error}
		<div class="empty-state" style="color: var(--red)">{error}</div>
	{:else if results}
		<header class="public-header">
			<div class="brand">
				<span class="brand-dot"></span>
				OpenXC Timing
			</div>
			<h1>{results.meet.name}</h1>
			<div class="meet-sub">
				{#if results.meet.date}{formatDate(results.meet.date)}{/if}
				{#if results.meet.location}&nbsp;·&nbsp;{results.meet.location}{/if}
			</div>
		</header>

		<main class="public-body">
			{#if results.races.length === 0}
				<div class="empty-state">Results will appear here once races are added.</div>
			{:else}
				{#each results.races as raceResults (raceResults.race.id)}
					<ResultsView {raceResults} showRaceLink />
				{/each}
			{/if}
		</main>

		<footer class="public-footer">Live results — refreshes automatically every 15 seconds.</footer>
	{/if}
</div>

<style>
	:global(body) {
		background: var(--bg);
	}

	.public-page {
		max-width: 1100px;
		margin: 0 auto;
		padding: 32px 20px 60px;
	}

	.public-header {
		margin-bottom: 28px;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 700;
		font-size: 13px;
		color: var(--text-muted);
		margin-bottom: 14px;
	}

	.brand-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 8px var(--accent);
	}

	.public-header h1 {
		font-size: 26px;
	}

	.meet-sub {
		color: var(--text-muted);
		margin-top: 6px;
		font-size: 14px;
	}

	.public-footer {
		text-align: center;
		color: var(--text-faint);
		font-size: 12px;
		margin-top: 20px;
	}
</style>
