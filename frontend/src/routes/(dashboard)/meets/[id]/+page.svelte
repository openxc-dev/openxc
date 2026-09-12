<script>
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { formatDate } from '$lib/format';
	import { meetsStore } from '$lib/stores';
	import MeetInfoTab from '$lib/components/MeetInfoTab.svelte';
	import AthletesTab from '$lib/components/AthletesTab.svelte';
	import RacesTab from '$lib/components/RacesTab.svelte';
	import TeamsTab from '$lib/components/TeamsTab.svelte';
	import TimeEntryTab from '$lib/components/TimeEntryTab.svelte';
	import FinishOrderTab from '$lib/components/FinishOrderTab.svelte';
	import ResultsTab from '$lib/components/ResultsTab.svelte';

	$: meetId = $page.params.id;

	let meet = null;
	let races = [];
	let teams = [];
	let loading = true;
	let error = '';
	let activeTab = 'teams';

	const tabs = [
		{ id: 'info', label: 'Meet Info' },
		{ id: 'teams', label: 'Teams' },
		{ id: 'races', label: 'Races' },
		{ id: 'athletes', label: 'Athletes' },
		{ id: 'time-entry', label: 'Time Entry' },
		{ id: 'finish-order', label: 'Finish Order' },
		{ id: 'results', label: 'Results' }
	];

	async function loadAll(id) {
		loading = true;
		error = '';
		try {
			[meet, races, teams] = await Promise.all([api.getMeet(id), api.listRaces(id), api.listTeams(id)]);
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	async function refreshRaces() {
		races = await api.listRaces(meetId);
	}

	async function refreshTeams() {
		teams = await api.listTeams(meetId);
	}

	async function refreshMeet() {
		meet = await api.getMeet(meetId);
		await meetsStore.refresh();
	}

	$: if (meetId) loadAll(meetId);

	const tabShortcuts = {
		i: 'info',
		e: 'teams',
		a: 'athletes',
		r: 'races',
		t: 'time-entry',
		f: 'finish-order',
		s: 'results'
	};

	function handleKeydown(e) {
		if (!e.altKey) return;
		const tabId = tabShortcuts[e.key.toLowerCase()];
		if (tabId) {
			e.preventDefault();
			activeTab = tabId;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

{#if loading}
	<div class="empty-state" style="height: 100%;">Loading…</div>
{:else if error}
	<div class="empty-state" style="height: 100%;">
		<p style="color: var(--red)">{error}</p>
	</div>
{:else if meet}
	<div class="meet-page">
		<header class="meet-header">
			<div>
				<h1>{meet.name}</h1>
				<div class="meet-sub">
					{#if meet.date}{formatDate(meet.date)}{/if}
					{#if meet.location}&nbsp;·&nbsp;{meet.location}{/if}
				</div>
			</div>
			<a class="btn" href="/results/{meet.id}" target="_blank" rel="noreferrer">
				View Public Results ↗
			</a>
		</header>

		<nav class="tabs">
			{#each tabs as tab}
				<button class="tab" class:active={activeTab === tab.id} on:click={() => (activeTab = tab.id)}>
					{tab.label}
				</button>
			{/each}
		</nav>

		<div class="tab-content">
			{#if activeTab === 'info'}
				<MeetInfoTab {meetId} {meet} onChanged={refreshMeet} />
			{:else if activeTab === 'teams'}
				<TeamsTab {meetId} {teams} onChanged={refreshTeams} />
			{:else if activeTab === 'athletes'}
				<AthletesTab {meetId} {races} {teams} />
			{:else if activeTab === 'races'}
				<RacesTab {meetId} {races} onChanged={refreshRaces} />
			{:else if activeTab === 'time-entry'}
				<TimeEntryTab {meetId} {races} />
			{:else if activeTab === 'finish-order'}
				<FinishOrderTab {races} />
			{:else if activeTab === 'results'}
				<ResultsTab {meetId} />
			{/if}
		</div>
	</div>
{/if}

<style>
	.meet-page {
		display: flex;
		flex-direction: column;
		height: 100%;
		min-height: 100vh;
	}

	.meet-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		padding: 24px 28px 18px;
		gap: 16px;
	}

	.meet-header h1 {
		font-size: 22px;
	}

	.meet-sub {
		color: var(--text-muted);
		font-size: 13px;
		margin-top: 4px;
	}

	.tabs {
		display: flex;
		gap: 4px;
		padding: 0 28px;
		border-bottom: 1px solid var(--border);
	}

	.tab {
		background: none;
		border: none;
		padding: 10px 16px;
		color: var(--text-muted);
		font-weight: 500;
		font-size: 13.5px;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
	}

	.tab:hover {
		color: var(--text);
	}

	.tab.active {
		color: var(--accent);
		border-bottom-color: var(--accent);
	}

	.tab-content {
		flex: 1;
		padding: 20px 28px 40px;
		min-height: 0;
	}

	@media (max-width: 820px) {
		.meet-header {
			flex-direction: column;
		}
		.tab-content,
		.meet-header {
			padding-left: 16px;
			padding-right: 16px;
		}
		.tabs {
			padding-left: 16px;
			padding-right: 16px;
			overflow-x: auto;
		}
	}
</style>
