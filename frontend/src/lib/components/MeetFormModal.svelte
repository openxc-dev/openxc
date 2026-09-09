<script>
	import Modal from './Modal.svelte';
	import { api } from '../api';

	export let meet = null;
	export let onClose = () => {};
	export let onSaved = () => {};

	let name = meet?.name ?? '';
	let date = meet?.date ?? '';
	let location = meet?.location ?? '';
	let notes = meet?.notes ?? '';
	let saving = false;
	let error = '';

	async function save() {
		if (!name.trim()) {
			error = 'Name is required';
			return;
		}
		saving = true;
		error = '';
		const payload = { name: name.trim(), date: date || null, location: location || null, notes: notes || null };
		try {
			if (meet) {
				await api.updateMeet(meet.id, payload);
			} else {
				await api.createMeet(payload);
			}
			onSaved();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<Modal title={meet ? 'Edit Meet' : 'New Meet'} {onClose}>
	<form class="form" on:submit|preventDefault={save}>
		<div class="field">
			<label for="meet-name">Meet name</label>
			<input id="meet-name" class="input" bind:value={name} placeholder="Riverside Invitational" autofocus />
		</div>
		<div class="field">
			<label for="meet-date">Date</label>
			<input id="meet-date" class="input" type="date" bind:value={date} />
		</div>
		<div class="field">
			<label for="meet-location">Location</label>
			<input id="meet-location" class="input" bind:value={location} placeholder="Riverside Park" />
		</div>
		<div class="field">
			<label for="meet-notes">Notes</label>
			<textarea id="meet-notes" class="input" rows="3" bind:value={notes}></textarea>
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
