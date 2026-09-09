<script>
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto, invalidateAll } from '$app/navigation';
	import { meetsStore } from '$lib/stores';
	import { formatDate } from '$lib/format';
	import { api } from '$lib/api';
	import MeetFormModal from '$lib/components/MeetFormModal.svelte';

	export let data;

	$: authenticated = data.authenticated;
	// No banner on a fresh install with zero meets yet — there's nothing
	// for a start/finish to be lost against, and the empty-state screen
	// already tells the operator to create a first meet.
	$: showNoActiveMeetBanner = $meetsStore.length > 0 && !$meetsStore.some((m) => m.is_active);

	let showForm = false;
	let editingMeet = null;
	let deletingMeet = null;
	let error = '';

	let passcode = '';
	let loginError = '';
	let loggingIn = false;

	onMount(() => {
		if (authenticated) meetsStore.refresh();
	});

	async function login() {
		loggingIn = true;
		loginError = '';
		try {
			const res = await fetch('/auth/login', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ passcode })
			});
			if (!res.ok) {
				loginError = 'Incorrect passcode';
				return;
			}
			passcode = '';
			await invalidateAll();
			await meetsStore.refresh();
		} catch (e) {
			loginError = e.message;
		} finally {
			loggingIn = false;
		}
	}

	function openCreate() {
		editingMeet = null;
		showForm = true;
	}

	function openEdit(meet, e) {
		e.preventDefault();
		e.stopPropagation();
		editingMeet = meet;
		showForm = true;
	}

	async function onSaved() {
		showForm = false;
		await meetsStore.refresh();
	}

	async function confirmDelete() {
		if (!deletingMeet) return;
		const wasCurrent = $page.params.id === deletingMeet.id;
		await api.deleteMeet(deletingMeet.id);
		deletingMeet = null;
		await meetsStore.refresh();
		if (wasCurrent) goto('/');
	}

	async function toggleActive(meet, e) {
		// Both preventDefault and stopPropagation are needed here, not just
		// one: this checkbox sits inside the meet's <a href> row, and
		// stopPropagation alone doesn't stop the browser's native anchor
		// navigation (that's gated on preventDefault, independent of
		// whether the event kept bubbling to JS listeners). We also skip
		// the native checkbox toggle entirely and drive `checked` purely
		// from server state, refreshed below.
		e.preventDefault();
		e.stopPropagation();
		error = '';
		try {
			await api.updateMeet(meet.id, { is_active: !meet.is_active });
		} catch (err) {
			error = err.message;
		} finally {
			await meetsStore.refresh();
		}
	}

	function handleKeydown(e) {
		if (e.key === 'Escape' && deletingMeet) {
			deletingMeet = null;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

{#if !authenticated}
	<div class="passcode-screen">
		<form class="card passcode-card" on:submit|preventDefault={login}>
			<div class="brand">
				<span class="brand-dot"></span>
				OpenXC Timing
			</div>
			<p class="passcode-hint">Enter the operator passcode to manage meets.</p>
			<div class="field">
				<label for="passcode">Passcode</label>
				<input
					id="passcode"
					class="input"
					type="password"
					bind:value={passcode}
					autofocus
				/>
			</div>
			{#if loginError}<p class="error">{loginError}</p>{/if}
			<button type="submit" class="btn btn-primary" disabled={loggingIn || !passcode}>
				{loggingIn ? 'Checking…' : 'Unlock'}
			</button>
		</form>
	</div>
{:else}
	<div class="app-shell">
		{#if showNoActiveMeetBanner}
			<div class="active-meet-banner">
				No meet is currently active — any starts or finishes submitted right
				now will be lost. Toggle a meet active in the sidebar below to fix
				this.
			</div>
		{/if}
		<div class="shell">
			<aside class="sidebar scrollbar-thin">
				<div class="sidebar-header">
					<div class="brand">
						<span class="brand-dot"></span>
						OpenXC Timing
					</div>
					<button class="btn btn-primary btn-sm" on:click={openCreate}>+ New Meet</button>
				</div>

				{#if error}<p class="sidebar-error">{error}</p>{/if}

				<nav class="meet-list">
					{#each $meetsStore as meet (meet.id)}
						<a
							href="/meets/{meet.id}"
							class="meet-item"
							class:active={$page.params.id === meet.id}
						>
							<div class="meet-item-main">
								<div class="meet-name">
									<span class="meet-name-text">{meet.name}</span>
									{#if meet.is_active}<span class="badge badge-accent active-badge">Active</span>{/if}
								</div>
								<div class="meet-meta">
									{#if meet.date}{formatDate(meet.date)} · {/if}{meet.race_count} races · {meet.athlete_count} athletes
								</div>
							</div>
							<div class="meet-item-controls">
								<label
									class="active-toggle"
									title={meet.is_active ? 'Active meet — click to deactivate' : 'Set as the active meet'}
									on:click={(e) => toggleActive(meet, e)}
								>
									<input
										type="checkbox"
										checked={meet.is_active}
										aria-label="Set {meet.name} as the active meet"
										tabindex="-1"
									/>
									<span class="toggle-track"><span class="toggle-thumb"></span></span>
								</label>
								<div class="meet-item-actions">
									<button class="icon-btn" title="Edit meet" on:click={(e) => openEdit(meet, e)}>✎</button>
									<button
										class="icon-btn danger"
										title="Delete meet"
										on:click={(e) => {
											e.preventDefault();
											e.stopPropagation();
											deletingMeet = meet;
										}}>🗑</button
									>
								</div>
							</div>
						</a>
					{:else}
						<div class="empty-sidebar">No meets yet. Create one to get started.</div>
					{/each}
				</nav>

				<a
					href="/readers"
					class="sidebar-footer-link"
					class:active={$page.url.pathname.startsWith('/readers')}
				>
					<span class="footer-link-icon">📡</span>
					Readers
				</a>
			</aside>

			<main class="content">
				<slot />
			</main>
		</div>
	</div>

	{#if showForm}
		<MeetFormModal meet={editingMeet} onClose={() => (showForm = false)} {onSaved} />
	{/if}

	{#if deletingMeet}
		<div class="overlay" on:click={() => (deletingMeet = null)} role="presentation">
			<div class="confirm card" on:click|stopPropagation role="dialog" aria-modal="true">
				<h3>Delete "{deletingMeet.name}"?</h3>
				<p class="confirm-text">This permanently deletes all races, athletes, and results for this meet.</p>
				<div class="actions">
					<button class="btn" on:click={() => (deletingMeet = null)}>Cancel</button>
					<button class="btn btn-danger" on:click={confirmDelete}>Delete Meet</button>
				</div>
			</div>
		</div>
	{/if}

{/if}

<style>
	.passcode-screen {
		height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 20px;
	}

	.passcode-card {
		width: 100%;
		max-width: 340px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.passcode-card .brand {
		justify-content: center;
	}

	.passcode-hint {
		color: var(--text-muted);
		font-size: 13px;
		margin: -8px 0 0;
		text-align: center;
	}

	.passcode-card .error {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}

	.app-shell {
		display: flex;
		flex-direction: column;
		height: 100vh;
	}

	.active-meet-banner {
		flex-shrink: 0;
		padding: 8px 16px;
		background: rgba(245, 158, 11, 0.15);
		border-bottom: 1px solid rgba(245, 158, 11, 0.4);
		color: #fbbf24;
		font-size: 12.5px;
		text-align: center;
	}

	.shell {
		display: flex;
		flex: 1;
		min-height: 0;
	}

	.sidebar {
		width: 300px;
		flex-shrink: 0;
		background: var(--bg-elevated);
		border-right: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		overflow-y: auto;
	}

	.sidebar-header {
		padding: 18px 16px 14px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		border-bottom: 1px solid var(--border);
		position: sticky;
		top: 0;
		background: var(--bg-elevated);
		z-index: 1;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 700;
		font-size: 15px;
		letter-spacing: -0.01em;
	}

	.brand-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 10px var(--accent);
	}

	.meet-list {
		padding: 8px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.meet-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 10px 10px;
		border-radius: 8px;
		color: var(--text);
	}

	.meet-item:hover {
		background: var(--bg-hover);
	}

	.meet-item.active {
		background: var(--accent-soft);
	}

	.meet-item.active .meet-name {
		color: #4ade80;
	}

	.meet-item-main {
		min-width: 0;
	}

	.meet-name {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
		font-weight: 600;
		font-size: 13.5px;
	}

	.meet-name-text {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.active-badge {
		flex-shrink: 0;
	}

	.meet-meta {
		font-size: 11.5px;
		color: var(--text-muted);
		margin-top: 2px;
	}

	.meet-item-controls {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-shrink: 0;
	}

	.meet-item-actions {
		display: flex;
		gap: 2px;
		flex-shrink: 0;
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.1s;
	}

	.meet-item:hover .meet-item-actions {
		opacity: 1;
		pointer-events: auto;
	}

	.active-toggle {
		display: flex;
		align-items: center;
		cursor: pointer;
	}

	.active-toggle input {
		position: absolute;
		opacity: 0;
		width: 0;
		height: 0;
	}

	.toggle-track {
		position: relative;
		width: 30px;
		height: 18px;
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 999px;
		flex-shrink: 0;
		transition: background 0.15s, border-color 0.15s;
	}

	.toggle-thumb {
		position: absolute;
		top: 1px;
		left: 1px;
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: var(--text-faint);
		transition: transform 0.15s, background 0.15s;
	}

	.active-toggle input:checked + .toggle-track {
		background: var(--accent-soft);
		border-color: var(--accent);
	}

	.active-toggle input:checked + .toggle-track .toggle-thumb {
		transform: translateX(12px);
		background: var(--accent);
	}

	.sidebar-error {
		margin: 0 8px 8px;
		padding: 8px 10px;
		border-radius: 8px;
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid rgba(239, 68, 68, 0.3);
		color: #fca5a5;
		font-size: 12px;
	}

	.icon-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		padding: 4px 6px;
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

	.empty-sidebar {
		padding: 20px 12px;
		color: var(--text-faint);
		font-size: 12.5px;
		text-align: center;
	}

	.sidebar-footer-link {
		margin-top: auto;
		position: sticky;
		bottom: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 16px;
		border-top: 1px solid var(--border);
		background: var(--bg-elevated);
		color: var(--text-muted);
		font-weight: 500;
		font-size: 13.5px;
	}

	.sidebar-footer-link:hover {
		background: var(--bg-hover);
		color: var(--text);
	}

	.sidebar-footer-link.active {
		color: var(--accent);
	}

	.footer-link-icon {
		font-size: 14px;
	}

	.content {
		flex: 1;
		overflow-y: auto;
		min-width: 0;
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

	.confirm h3 {
		margin-bottom: 8px;
	}

	.confirm-text {
		color: var(--text-muted);
		font-size: 13.5px;
		margin: 0 0 18px;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}

	@media (max-width: 820px) {
		.app-shell {
			height: auto;
			min-height: 100vh;
		}
		.shell {
			flex-direction: column;
		}
		.sidebar {
			width: 100%;
			max-height: 260px;
		}
	}
</style>
