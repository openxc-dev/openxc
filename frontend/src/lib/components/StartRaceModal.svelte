<script>
	import { onDestroy, onMount, tick } from 'svelte';
	import Modal from './Modal.svelte';
	import { api } from '../api';
	import { formatClock, parseTimeToSeconds } from '../format';

	export let meetId;
	export let race;
	export let onClose = () => {};
	export let onStarted = () => {};

	let starts = [];
	let loadingStarts = true;
	let selected = 'elapsed';
	let elapsedInput = '';
	let elapsedInputEl;
	let saving = false;
	let error = '';

	// Keeps the elapsed-time readouts ticking while the dialog stays open.
	let nowTick = Date.now();
	const tickInterval = setInterval(() => (nowTick = Date.now()), 1000);
	onDestroy(() => clearInterval(tickInterval));

	onMount(async () => {
		elapsedInputEl?.focus();
		try {
			starts = await api.listStarts(meetId);
		} catch (e) {
			error = e.message;
		} finally {
			loadingStarts = false;
		}
	});

	async function selectElapsed() {
		selected = 'elapsed';
		await tick();
		elapsedInputEl?.focus();
	}

	function formatTimeOfDay(iso) {
		return new Date(iso).toLocaleTimeString(undefined, {
			hour: 'numeric',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function formatElapsedSince(iso, now) {
		const deltaSeconds = (now - new Date(iso).getTime()) / 1000;
		if (deltaSeconds < 0) return `in ${formatClock(-deltaSeconds)}`;
		return formatClock(deltaSeconds);
	}

	async function submit() {
		error = '';
		let startTime;

		if (selected === 'elapsed') {
			let elapsedSeconds = 0;
			if (elapsedInput.trim()) {
				const parsed = parseTimeToSeconds(elapsedInput);
				if (parsed === null) {
					error = 'Enter the elapsed time as seconds (e.g. 120) or minutes:seconds (e.g. 2:00)';
					return;
				}
				elapsedSeconds = parsed;
			}
			startTime = new Date(Date.now() - elapsedSeconds * 1000);
		} else {
			const start = starts.find((s) => s.id === selected);
			startTime = start ? new Date(start.time) : new Date();
		}

		saving = true;
		try {
			await api.updateRace(race.id, { start_time: startTime.toISOString() });
			onStarted();
		} catch (e) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<Modal title="Start {race.name}" onClose={onClose} width="420px">
	<form class="form" on:submit|preventDefault={submit}>
		<div class="field">
			<span class="label">Start reference</span>
			<div class="options scrollbar-thin">
				<label class="option elapsed-option">
					<input type="radio" name="start-source" value="elapsed" bind:group={selected} />
					<span>Started</span>
					<input
						class="input elapsed-input"
						placeholder="0"
						bind:value={elapsedInput}
						bind:this={elapsedInputEl}
						on:focus={selectElapsed}
					/>
					<span>ago</span>
				</label>

				{#if loadingStarts}
					<p class="muted">Loading starts…</p>
				{:else}
					{#each starts as start (start.id)}
						<label class="option">
							<input type="radio" name="start-source" value={start.id} bind:group={selected} />
							<span class="start-option-text">
								{#if start.label}<strong>{start.label}</strong> —{/if}
								{formatTimeOfDay(start.time)}
								<span class="relative-time">— {formatElapsedSince(start.time, nowTick)}</span>
							</span>
						</label>
					{/each}
				{/if}
			</div>
			<p class="hint">
				Enter seconds (<code>120</code>) or minutes:seconds (<code>2:00</code>) — handy for timing
				the gun with a stopwatch and entering it once you're back at the computer. Leave it blank
				(or 0) if the gun is going off right now.
			</p>
		</div>

		{#if error}<p class="error">{error}</p>{/if}

		<div class="actions">
			<button type="button" class="btn" on:click={onClose}>Cancel</button>
			<button type="submit" class="btn btn-primary" disabled={saving}>
				{saving ? 'Starting…' : 'Start Race'}
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
	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.label {
		font-size: 12px;
		color: var(--text-muted);
		font-weight: 500;
	}
	.options {
		display: flex;
		flex-direction: column;
		gap: 2px;
		max-height: 180px;
		overflow-y: auto;
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 6px;
	}
	.option {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 7px 8px;
		border-radius: 6px;
		font-size: 13.5px;
		cursor: pointer;
	}
	.option:hover {
		background: var(--bg-hover);
	}
	.elapsed-option {
		flex-wrap: wrap;
	}
	.start-option-text {
		flex: 1;
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.relative-time {
		color: var(--text-faint);
	}
	.elapsed-input {
		width: 90px;
		padding: 4px 8px;
	}
	.hint {
		font-size: 11.5px;
		color: var(--text-faint);
		line-height: 1.5;
		margin: 0;
	}
	.hint code {
		background: var(--bg-elevated);
		padding: 1px 5px;
		border-radius: 4px;
		color: var(--text-muted);
	}
	.muted {
		color: var(--text-muted);
		font-size: 12.5px;
		padding: 6px 8px;
		margin: 0;
	}
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 4px;
	}
	.error {
		color: var(--red);
		font-size: 13px;
		margin: 0;
	}
</style>
