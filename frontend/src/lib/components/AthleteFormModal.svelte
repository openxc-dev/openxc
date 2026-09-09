<script>
	import Modal from './Modal.svelte';
	import { api } from '../api';

	export let meetId;
	export let races = [];
	export let teams = [];
	export let athlete = null;
	export let onClose = () => {};
	export let onSaved = () => {};

	let bib = athlete?.bib ?? '';
	let first_name = athlete?.first_name ?? '';
	let last_name = athlete?.last_name ?? '';
	let team_id = athlete?.team_id ?? '';
	let grade = athlete?.grade ?? '';
	let race_id = athlete?.race_id ?? '';
	let saving = false;
	let error = '';

	async function save() {
		if (!bib.trim() || !first_name.trim() || !last_name.trim()) {
			error = 'Bib, first name, and last name are required';
			return;
		}
		saving = true;
		error = '';
		const payload = {
			bib: bib.trim(),
			first_name: first_name.trim(),
			last_name: last_name.trim(),
			team_id: team_id || null,
			grade: grade || null,
			race_id: race_id || null
		};
		try {
			if (athlete) {
				await api.updateAthlete(athlete.id, payload);
			} else {
				await api.createAthlete(meetId, payload);
			}
			onSaved();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<Modal title={athlete ? 'Edit Athlete' : 'Add Athlete'} onClose={onClose} width="420px">
	<form class="form" on:submit|preventDefault={save}>
		<div class="row">
			<div class="field">
				<label for="a-bib">Bib #</label>
				<input id="a-bib" class="input" bind:value={bib} autofocus />
			</div>
			<div class="field">
				<label for="a-grade">Grade</label>
				<input id="a-grade" class="input" bind:value={grade} placeholder="11" />
			</div>
		</div>
		<div class="row">
			<div class="field">
				<label for="a-first">First name</label>
				<input id="a-first" class="input" bind:value={first_name} />
			</div>
			<div class="field">
				<label for="a-last">Last name</label>
				<input id="a-last" class="input" bind:value={last_name} />
			</div>
		</div>
		<div class="field">
			<label for="a-team">Team / School</label>
			<select id="a-team" class="select" bind:value={team_id}>
				<option value="">Unassigned</option>
				{#each teams as team}
					<option value={team.id}>{team.name}</option>
				{/each}
			</select>
		</div>
		<div class="field">
			<label for="a-race">Race</label>
			<select id="a-race" class="select" bind:value={race_id}>
				<option value="">Unassigned</option>
				{#each races as race}
					<option value={race.id}>{race.name}</option>
				{/each}
			</select>
		</div>

		{#if error}<p class="error">{error}</p>{/if}

		<div class="actions">
			<button type="button" class="btn" on:click={onClose}>Cancel</button>
			<button type="submit" class="btn btn-primary" disabled={saving}>
				{saving ? 'Saving…' : 'Save'}
			</button>
		</div>
	</form>
</Modal>

<style>
	.form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 8px;
	}
	.error {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}
</style>
