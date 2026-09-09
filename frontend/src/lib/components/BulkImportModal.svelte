<script>
	import Modal from './Modal.svelte';
	import { api } from '../api';

	export let meetId;
	export let races = [];
	export let teams = [];
	export let onClose = () => {};
	export let onSaved = () => {};

	let defaultRaceId = '';
	let defaultTeamId = '';
	let text = '';
	let saving = false;
	let error = '';
	let preview = [];

	$: preview = parse(text);

	function parse(raw) {
		return raw
			.split('\n')
			.map((line) => line.trim())
			.filter(Boolean)
			.map((line) => {
				const parts = line.split(/\t|,/).map((p) => p.trim());
				const [bib, first_name, last_name, teamName, grade, raceName] = parts;

				let race_id = defaultRaceId || null;
				if (raceName) {
					const match = races.find((r) => r.name.toLowerCase() === raceName.toLowerCase());
					if (match) race_id = match.id;
				}

				let team_id = defaultTeamId || null;
				if (teamName) {
					const match = teams.find((t) => t.name.toLowerCase() === teamName.toLowerCase());
					if (match) team_id = match.id;
				}

				return { bib, first_name, last_name, team_id, grade: grade || null, race_id };
			});
	}

	async function submit() {
		const rows = preview.filter((r) => r.bib && r.first_name && r.last_name);
		if (rows.length === 0) {
			error = 'No valid rows to import';
			return;
		}
		saving = true;
		error = '';
		try {
			await api.bulkCreateAthletes(meetId, rows);
			onSaved();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<Modal title="Bulk Import Athletes" onClose={onClose} width="640px">
	<div class="form">
		<p class="hint">
			Paste one athlete per line, comma or tab separated:
			<code>bib, first name, last name, team, grade, race name</code>
			Team, grade, and race name are optional — a team or race name that doesn't match one you've
			already created falls back to the defaults below.
		</p>

		<div class="row">
			<div class="field">
				<label for="bulk-default-team">Default team (used when a row omits or doesn't match one)</label>
				<select id="bulk-default-team" class="select" bind:value={defaultTeamId}>
					<option value="">None</option>
					{#each teams as team}
						<option value={team.id}>{team.name}</option>
					{/each}
				</select>
			</div>
			<div class="field">
				<label for="bulk-default-race">Default race (used when a row omits or doesn't match one)</label>
				<select id="bulk-default-race" class="select" bind:value={defaultRaceId}>
					<option value="">None</option>
					{#each races as race}
						<option value={race.id}>{race.name}</option>
					{/each}
				</select>
			</div>
		</div>

		<div class="field">
			<label for="bulk-text">Athletes</label>
			<textarea
				id="bulk-text"
				class="input mono"
				rows="8"
				bind:value={text}
				placeholder={'101, Ava, Smith, Lincoln HS, 11, Girls Varsity\n102, Liam, Johnson, Roosevelt HS, 12, Boys Varsity'}
			></textarea>
		</div>

		{#if preview.length > 0}
			<div class="preview-wrap scrollbar-thin">
				<table>
					<thead>
						<tr>
							<th>Bib</th>
							<th>First</th>
							<th>Last</th>
							<th>Team</th>
							<th>Grade</th>
							<th>Race</th>
						</tr>
					</thead>
					<tbody>
						{#each preview as row}
							<tr class:invalid={!(row.bib && row.first_name && row.last_name)}>
								<td>{row.bib || '—'}</td>
								<td>{row.first_name || '—'}</td>
								<td>{row.last_name || '—'}</td>
								<td>{teams.find((t) => t.id === row.team_id)?.name || '—'}</td>
								<td>{row.grade || '—'}</td>
								<td>{races.find((r) => r.id === row.race_id)?.name || '—'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if error}<p class="error">{error}</p>{/if}

		<div class="actions">
			<button type="button" class="btn" on:click={onClose}>Cancel</button>
			<button
				type="button"
				class="btn btn-primary"
				disabled={saving || preview.length === 0}
				on:click={submit}
			>
				{saving ? 'Importing…' : `Import ${preview.length} Athletes`}
			</button>
		</div>
	</div>
</Modal>

<style>
	.form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.hint {
		font-size: 12.5px;
		color: var(--text-muted);
		margin: 0;
		line-height: 1.6;
	}
	.hint code {
		display: block;
		margin-top: 4px;
		color: var(--text);
		background: var(--bg-elevated);
		padding: 4px 8px;
		border-radius: 6px;
		font-size: 12px;
	}
	.row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
	}
	.mono {
		font-family: 'SF Mono', Menlo, Consolas, monospace;
		font-size: 12.5px;
	}
	.preview-wrap {
		max-height: 220px;
		overflow-y: auto;
		border: 1px solid var(--border);
		border-radius: 8px;
	}
	.preview-wrap table {
		font-size: 12.5px;
	}
	tr.invalid {
		color: var(--red);
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}
	.error {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}
</style>
