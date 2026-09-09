<script>
	import Modal from './Modal.svelte';
	import { api } from '../api';
	import { formatTime, parseTimeToSeconds } from '../format';

	export let finisher;
	export let onClose = () => {};
	export let onSaved = () => {};

	let bib = finisher.bib ?? '';
	let timeText = finisher.time_seconds != null ? formatTime(finisher.time_seconds) : '';
	let status = finisher.status;
	let notes = finisher.notes ?? '';
	let saving = false;
	let error = '';

	async function save() {
		saving = true;
		error = '';
		const time_seconds = timeText.trim() ? parseTimeToSeconds(timeText) : null;
		try {
			await api.updateFinisher(finisher.id, {
				bib: bib.trim() || null,
				time_seconds,
				status,
				notes: notes || null
			});
			onSaved();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<Modal title="Place {finisher.place} — Correction" onClose={onClose} width="380px">
	<form class="form" on:submit|preventDefault={save}>
		<div class="field">
			<label for="f-bib">Bib #</label>
			<input id="f-bib" class="input" bind:value={bib} placeholder="Leave blank if unknown" autofocus />
		</div>
		<div class="field">
			<label for="f-time">Time (m:ss.d)</label>
			<input id="f-time" class="input" bind:value={timeText} placeholder="18:24.3" />
		</div>
		<div class="field">
			<label for="f-status">Status</label>
			<select id="f-status" class="select" bind:value={status}>
				<option value="finished">Finished</option>
				<option value="dnf">DNF</option>
				<option value="dq">DQ</option>
			</select>
		</div>
		<div class="field">
			<label for="f-notes">Notes</label>
			<input id="f-notes" class="input" bind:value={notes} placeholder="Optional" />
		</div>

		{#if error}<p class="error">{error}</p>{/if}

		<div class="actions">
			<button type="button" class="btn" on:click={onClose}>Cancel</button>
			<button type="submit" class="btn btn-primary" disabled={saving}>
				{saving ? 'Saving…' : 'Save Correction'}
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
