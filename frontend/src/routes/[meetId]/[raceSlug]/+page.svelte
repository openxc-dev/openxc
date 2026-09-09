<script>
	import { page } from '$app/stores';
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';
	import { formatDate } from '$lib/format';
	import ResultsView from '$lib/components/ResultsView.svelte';

	$: meetId = $page.params.meetId;
	$: raceSlug = $page.params.raceSlug;

	let meet = null;
	let raceResults = null;
	let loading = true;
	let error = '';
	let refreshTimer;

	async function load() {
		error = '';
		try {
			[meet, raceResults] = await Promise.all([
				api.getMeet(meetId),
				api.getRaceResultsBySlug(meetId, raceSlug)
			]);
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
	<title>{raceResults ? `${raceResults.race.name} — Results` : 'Race Results'}</title>
</svelte:head>

<div class="public-page">
	{#if loading}
		<div class="empty-state">Loading results…</div>
	{:else if error}
		<div class="empty-state" style="color: var(--red)">{error}</div>
	{:else if meet && raceResults}
		<header class="public-header">
			<div class="brand">
				<span class="brand-dot"></span>
				OpenXC Timing
			</div>
			<div class="breadcrumb">
				<a href="/results/{meet.id}">{meet.name}</a>
				<span class="sep">/</span>
				{raceResults.race.name}
			</div>
			<h1>{raceResults.race.name}</h1>
			<div class="meet-sub">
				{#if meet.date}{formatDate(meet.date)}{/if}
				{#if meet.location}&nbsp;·&nbsp;{meet.location}{/if}
			</div>
		</header>

		<main class="public-body">
			<ResultsView {raceResults} />
		</main>

		<footer class="public-footer">
			Live results — refreshes automatically every 15 seconds.
			<span class="sep">·</span>
			<a href="/results/{meet.id}">View full meet results ↗</a>
		</footer>
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

	.breadcrumb {
		font-size: 12.5px;
		color: var(--text-muted);
		margin-bottom: 8px;
	}

	.breadcrumb a:hover {
		color: var(--accent);
		text-decoration: underline;
	}

	.sep {
		margin: 0 6px;
		color: var(--text-faint);
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

	.public-footer a:hover {
		color: var(--accent);
	}
</style>
