<script>
	import { api } from '../api';

	export let meetId;
	export let teams = [];
	export let onChanged = () => {};

	let creating = false;
	let newTeamName = '';
	let showBulk = false;
	let bulkNames = '';
	let editingId = null;
	let draftName = '';
	let error = '';
	let deletingTeam = null;
	let saving = false;

	// The `autofocus` HTML attribute doesn't reliably steal focus for a
	// form opened from a button click or keyboard shortcut — Chromium's
	// heuristic declines to move focus away from whatever the user just
	// interacted with. Focusing imperatively on mount works regardless.
	function autofocus(node) {
		node.focus();
	}

	async function createTeam() {
		const name = newTeamName.trim();
		if (!name) {
			error = 'Team name is required';
			return;
		}
		error = '';
		saving = true;
		try {
			await api.createTeam(meetId, { name });
			newTeamName = '';
			creating = false;
			await onChanged();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}

	$: bulkPreview = bulkNames
		.split('\n')
		.map((l) => l.trim())
		.filter(Boolean);

	async function submitBulk() {
		if (bulkPreview.length === 0) return;
		error = '';
		saving = true;
		try {
			await api.bulkCreateTeams(meetId, bulkPreview);
			bulkNames = '';
			showBulk = false;
			await onChanged();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}

	function startEdit(team) {
		editingId = team.id;
		draftName = team.name;
	}

	function cancelEdit() {
		editingId = null;
	}

	async function saveEdit() {
		const name = draftName.trim();
		if (!name) {
			error = 'Team name is required';
			return;
		}
		error = '';
		try {
			await api.updateTeam(editingId, { name });
			editingId = null;
			await onChanged();
		} catch (e) {
			error = e.message;
		}
	}

	async function confirmDelete() {
		if (!deletingTeam) return;
		await api.deleteTeam(deletingTeam.id);
		deletingTeam = null;
		await onChanged();
	}

	function handleKeydown(e) {
		if (e.key === 'Escape') {
			if (deletingTeam) {
				deletingTeam = null;
			} else if (showBulk) {
				showBulk = false;
			} else if (creating) {
				creating = false;
			}
			return;
		}
		if (e.altKey && e.key.toLowerCase() === 'n') {
			e.preventDefault();
			creating = true;
		} else if (e.altKey && e.key.toLowerCase() === 'b') {
			e.preventDefault();
			showBulk = true;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="header-row">
	<h2>Teams <span class="count">({teams.length})</span></h2>
	<div class="header-actions">
		<button class="btn btn-sm" on:click={() => (showBulk = !showBulk)}>
			{showBulk ? 'Cancel' : 'Bulk Add'}
		</button>
		<button class="btn btn-primary btn-sm" on:click={() => (creating = !creating)}>
			{creating ? 'Cancel' : '+ Add Team'}
		</button>
	</div>
</div>

{#if error}<p class="error">{error}</p>{/if}

{#if creating}
	<div class="card inline-form">
		<input
			class="input"
			placeholder="Team name (e.g. Lincoln HS)"
			bind:value={newTeamName}
			on:keydown={(e) => e.key === 'Enter' && createTeam()}
			use:autofocus
		/>
		<button class="btn btn-primary btn-sm" on:click={createTeam} disabled={saving}>Add</button>
	</div>
{/if}

{#if showBulk}
	<div class="card inline-form bulk-form">
		<div class="field">
			<label for="bulk-teams">Team names, one per line</label>
			<textarea
				id="bulk-teams"
				class="input"
				rows="6"
				bind:value={bulkNames}
				use:autofocus
				placeholder={'Lincoln HS\nRoosevelt HS\nJefferson HS'}
			></textarea>
		</div>
		<button class="btn btn-primary btn-sm" on:click={submitBulk} disabled={saving || bulkPreview.length === 0}>
			Add {bulkPreview.length || ''} Team{bulkPreview.length === 1 ? '' : 's'}
		</button>
	</div>
{/if}

{#if teams.length === 0 && !creating && !showBulk}
	<div class="empty-state">
		<p>No teams yet. Add the teams invited to this meet so you can assign athletes to them.</p>
	</div>
{:else if teams.length > 0}
	<div class="table-wrap card scrollbar-thin">
		<table>
			<thead>
				<tr>
					<th>Name</th>
					<th>Athletes</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each teams as team (team.id)}
					<tr>
						<td class="name-cell">
							{#if editingId === team.id}
								<input
									class="input"
									bind:value={draftName}
									on:keydown={(e) => e.key === 'Enter' && saveEdit()}
									autofocus
								/>
							{:else}
								{team.name}
							{/if}
						</td>
						<td>{team.athlete_count}</td>
						<td class="actions-cell">
							{#if editingId === team.id}
								<button class="btn btn-sm" on:click={cancelEdit}>Cancel</button>
								<button class="btn btn-primary btn-sm" on:click={saveEdit}>Save</button>
							{:else}
								<button class="btn btn-sm" on:click={() => startEdit(team)}>Edit</button>
								<button class="btn btn-sm btn-danger" on:click={() => (deletingTeam = team)}>Delete</button>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

{#if deletingTeam}
	<div class="overlay" on:click={() => (deletingTeam = null)} role="presentation">
		<div class="confirm card" on:click|stopPropagation role="dialog" aria-modal="true">
			<h3>Delete "{deletingTeam.name}"?</h3>
			<p class="confirm-text">Athletes on this team will become unassigned. This does not delete athletes.</p>
			<div class="actions">
				<button class="btn" on:click={() => (deletingTeam = null)}>Cancel</button>
				<button class="btn btn-danger" on:click={confirmDelete}>Delete Team</button>
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

	.count {
		color: var(--text-muted);
		font-weight: 400;
	}

	.header-actions {
		display: flex;
		gap: 8px;
	}

	.error {
		color: var(--red);
		font-size: 13px;
	}

	.inline-form {
		padding: 14px 16px;
		margin-bottom: 14px;
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.bulk-form {
		flex-direction: column;
		align-items: stretch;
	}

	.bulk-form .field {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin-bottom: 12px;
	}

	.bulk-form label {
		font-size: 12px;
		color: var(--text-muted);
		font-weight: 500;
	}

	.bulk-form button {
		align-self: flex-end;
	}

	.table-wrap {
		overflow-x: auto;
	}

	.name-cell {
		font-weight: 500;
	}

	.actions-cell {
		display: flex;
		gap: 6px;
		justify-content: flex-end;
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
