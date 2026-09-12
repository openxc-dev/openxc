<script>
	import { api } from '../api';

	export let meetId;
	export let meet;
	export let onChanged = () => {};

	let name = meet.name;
	let date = meet.date ?? '';
	let location = meet.location ?? '';
	let notes = meet.notes ?? '';
	let saving = false;
	let error = '';
	let saved = false;

	async function save() {
		if (!name.trim()) {
			error = 'Name is required';
			return;
		}
		saving = true;
		error = '';
		saved = false;
		try {
			await api.updateMeet(meetId, {
				name: name.trim(),
				date: date || null,
				location: location || null,
				notes: notes || null
			});
			saved = true;
			await onChanged();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<div class="header-row">
	<h2>Meet Info</h2>
</div>

<div class="card form-card">
	<form class="form" on:submit|preventDefault={save}>
		<div class="field">
			<label for="info-name">Meet name</label>
			<input id="info-name" class="input" bind:value={name} placeholder="Riverside Invitational" />
		</div>
		<div class="field">
			<label for="info-date">Date</label>
			<input id="info-date" class="input" type="date" bind:value={date} />
		</div>
		<div class="field">
			<label for="info-location">Location</label>
			<input id="info-location" class="input" bind:value={location} placeholder="Riverside Park" />
		</div>
		<div class="field">
			<label for="info-notes">Notes</label>
			<textarea id="info-notes" class="input" rows="4" bind:value={notes}></textarea>
		</div>

		{#if error}<p class="error">{error}</p>{/if}
		{#if saved}<p class="success">Saved.</p>{/if}

		<div class="actions">
			<button type="submit" class="btn btn-primary" disabled={saving}>
				{saving ? 'Saving…' : 'Save'}
			</button>
		</div>
	</form>
</div>

<style>
	.header-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 16px;
	}

	.form-card {
		padding: 20px;
		max-width: 480px;
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.actions {
		display: flex;
		justify-content: flex-end;
		margin-top: 4px;
	}

	.error {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}

	.success {
		color: var(--accent);
		font-size: 13px;
		margin: 0;
	}
</style>
