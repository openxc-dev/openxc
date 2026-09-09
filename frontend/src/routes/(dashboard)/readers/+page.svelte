<script>
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';

	function formatTagTime(iso) {
		if (!iso) return '—';
		return new Date(iso).toLocaleTimeString(undefined, {
			hour12: false,
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	// Always show at least this many antenna badges (the common fixed-reader
	// port count), extending further only if a reader actually reports more
	// total ports (num_antennas). num_antennas is null until a successful
	// connect, so an unconnected reader shows every slot dull.
	const MIN_ANTENNA_SLOTS = 4;
	function antennaSlots(reader) {
		const count = Math.max(reader.num_antennas || 0, MIN_ANTENNA_SLOTS);
		const connected = reader.connected_antennas;
		return Array.from({ length: count }, (_, i) => {
			const id = i + 1;
			// connected_antennas is the real per-antenna "is something
			// actually plugged in" status — lit only for those specific
			// IDs. If the reader didn't report it (null), fall back to
			// treating every port up to num_antennas as lit, since that's
			// the best information available.
			const present = connected ? connected.includes(id) : id <= (reader.num_antennas || 0);
			return { id, present };
		});
	}

	let readers = [];
	let loading = true;
	let loadError = '';

	let creating = false;
	let newIp = '';
	let newLabel = '';
	let saving = false;
	let formError = '';

	let error = '';
	let busyLabel = null;
	let readingBusyLabel = null;

	let selectedLabel = null;
	let selectedTags = [];
	let selectedReading = false;
	let tagsError = '';
	let tagsPollHandle = null;

	async function refresh() {
		try {
			readers = await api.listReaders();
			loadError = '';
		} catch (e) {
			loadError = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(refresh);
	onDestroy(() => stopTagsPolling());

	async function createReader() {
		const ip_address = newIp.trim();
		if (!ip_address) {
			formError = 'IP address is required';
			return;
		}
		formError = '';
		saving = true;
		try {
			const label = newLabel.trim();
			await api.createReader({ ip_address, label: label || undefined });
			newIp = '';
			newLabel = '';
			creating = false;
			await refresh();
		} catch (e) {
			formError = e.message;
		} finally {
			saving = false;
		}
	}

	async function toggleConnection(reader) {
		error = '';
		busyLabel = reader.label;
		try {
			if (reader.status === 'connected') {
				await api.disconnectReader(reader.label);
			} else {
				await api.connectReader(reader.label);
			}
		} catch (e) {
			error = `${reader.label}: ${e.message}`;
		} finally {
			busyLabel = null;
			await refresh();
		}
	}

	async function toggleReading(reader) {
		error = '';
		readingBusyLabel = reader.label;
		try {
			if (reader.reading) {
				await api.stopReading(reader.label);
			} else {
				await api.startReading(reader.label);
				selectReader(reader.label);
			}
		} catch (e) {
			error = `${reader.label}: ${e.message}`;
		} finally {
			readingBusyLabel = null;
			await refresh();
		}
	}

	function stopTagsPolling() {
		if (tagsPollHandle) {
			clearInterval(tagsPollHandle);
			tagsPollHandle = null;
		}
	}

	async function pollTags() {
		if (!selectedLabel) return;
		try {
			const res = await api.listReaderTags(selectedLabel);
			selectedReading = res.reading;
			selectedTags = res.tags.slice().reverse();
			tagsError = '';
		} catch (e) {
			tagsError = e.message;
		}
	}

	function selectReader(label) {
		if (selectedLabel === label) {
			selectedLabel = null;
			stopTagsPolling();
			return;
		}
		selectedLabel = label;
		selectedTags = [];
		stopTagsPolling();
		pollTags();
		tagsPollHandle = setInterval(pollTags, 1500);
	}

	function handleKeydown(e) {
		if (e.key === 'Escape' && creating) {
			creating = false;
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="readers-page">
	<header class="page-header">
		<div>
			<h1>Readers</h1>
			<div class="page-sub">RFID (LLRP) readers for finish-line tag acquisition</div>
		</div>
	</header>

	<div class="page-content">
		<div class="header-row">
			<h2>Registered readers <span class="count">({readers.length})</span></h2>
			<button class="btn btn-primary btn-sm" on:click={() => (creating = !creating)}>
				{creating ? 'Cancel' : '+ Add Reader'}
			</button>
		</div>

		{#if error}<p class="error">{error}</p>{/if}

		{#if creating}
			<div class="card inline-form">
				<div class="field">
					<label for="reader-ip">IP address</label>
					<input
						id="reader-ip"
						class="input"
						placeholder="192.168.8.21"
						bind:value={newIp}
						on:keydown={(e) => e.key === 'Enter' && createReader()}
						autofocus
					/>
				</div>
				<div class="field">
					<label for="reader-label">Label (optional)</label>
					<input
						id="reader-label"
						class="input"
						placeholder="finish-line-north"
						bind:value={newLabel}
						on:keydown={(e) => e.key === 'Enter' && createReader()}
					/>
				</div>
				<button class="btn btn-primary btn-sm" on:click={createReader} disabled={saving}>
					{saving ? 'Adding…' : 'Add'}
				</button>
			</div>
			{#if formError}<p class="error">{formError}</p>{/if}
		{/if}

		{#if loading}
			<div class="empty-state">Loading…</div>
		{:else if loadError}
			<div class="empty-state">
				<p style="color: var(--red)">{loadError}</p>
			</div>
		{:else if readers.length === 0 && !creating}
			<div class="empty-state">
				<p>No readers registered yet. Add one with its IP address to get started.</p>
			</div>
		{:else if readers.length > 0}
			<div class="table-wrap card scrollbar-thin">
				<table>
					<thead>
						<tr>
							<th>Label</th>
							<th>IP address</th>
							<th>Manufacturer</th>
							<th>Product</th>
							<th>Antennas</th>
							<th>Status</th>
							<th>Reading</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{#each readers as reader (reader.id)}
							<tr class:selected={selectedLabel === reader.label}>
								<td class="name-cell">
									<button class="link-btn" on:click={() => selectReader(reader.label)}>
										{reader.label}
									</button>
								</td>
								<td>{reader.ip_address}</td>
								<td>{reader.manufacturer ?? '—'}</td>
								<td>{reader.product ?? '—'}</td>
								<td>
								<div class="antenna-badges">
									{#each antennaSlots(reader) as slot (slot.id)}
										<span class="antenna-badge" class:present={slot.present}>{slot.id}</span>
									{/each}
								</div>
							</td>
								<td>
									<span class="badge" class:badge-accent={reader.status === 'connected'}>
										{reader.status}
									</span>
								</td>
								<td>
									{#if reader.reading}
										<span class="badge badge-accent">reading</span>
									{:else}
										<span class="badge">idle</span>
									{/if}
								</td>
								<td class="actions-cell">
									<button
										class="btn btn-sm"
										class:btn-primary={reader.status !== 'connected'}
										disabled={busyLabel === reader.label}
										on:click={() => toggleConnection(reader)}
									>
										{#if busyLabel === reader.label}
											…
										{:else if reader.status === 'connected'}
											Disconnect
										{:else}
											Connect
										{/if}
									</button>
									<button
										class="btn btn-sm"
										class:btn-primary={!reader.reading}
										disabled={readingBusyLabel === reader.label}
										on:click={() => toggleReading(reader)}
									>
										{#if readingBusyLabel === reader.label}
											…
										{:else if reader.reading}
											Stop
										{:else}
											Start
										{/if}
									</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}

		{#if selectedLabel}
			<div class="card tags-panel">
				<div class="tags-header">
					<h3>
						Tag reads — {selectedLabel}
						{#if selectedReading}<span class="badge badge-accent">reading</span>{/if}
					</h3>
					<button class="btn btn-sm" on:click={() => selectReader(selectedLabel)}>Close</button>
				</div>
				{#if tagsError}<p class="error">{tagsError}</p>{/if}
				{#if selectedTags.length === 0}
					<div class="empty-state">
						<p>
							{selectedReading
								? 'Waiting for tag reads…'
								: 'No tag reads yet. Click Start to begin reading.'}
						</p>
					</div>
				{:else}
					<div class="tags-list scrollbar-thin">
						<table>
							<thead>
								<tr>
									<th>Tag</th>
									<th>Antenna</th>
									<th>RSSI</th>
									<th>Time</th>
								</tr>
							</thead>
							<tbody>
								{#each selectedTags as t, i (i)}
									<tr>
										<td class="name-cell">{t.tag}</td>
										<td>{t.antenna_id ?? '—'}</td>
										<td>{t.peak_rssi ?? '—'}</td>
										<td>{formatTagTime(t.time)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	.readers-page {
		display: flex;
		flex-direction: column;
		height: 100%;
		min-height: 100vh;
	}

	.page-header {
		padding: 24px 28px 18px;
	}

	.page-header h1 {
		font-size: 22px;
	}

	.page-sub {
		color: var(--text-muted);
		font-size: 13px;
		margin-top: 4px;
	}

	.page-content {
		flex: 1;
		padding: 4px 28px 40px;
		min-height: 0;
	}

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

	.error {
		color: var(--red);
		font-size: 13px;
	}

	.inline-form {
		padding: 14px 16px;
		margin-bottom: 14px;
		display: flex;
		align-items: flex-end;
		gap: 10px;
		flex-wrap: wrap;
	}

	.inline-form .field {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.inline-form label {
		font-size: 12px;
		color: var(--text-muted);
		font-weight: 500;
	}

	.table-wrap {
		overflow-x: auto;
	}

	.name-cell {
		font-weight: 500;
	}

	.antenna-badges {
		display: flex;
		gap: 4px;
	}

	.antenna-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 20px;
		height: 20px;
		padding: 0 4px;
		border-radius: 6px;
		font-size: 11px;
		font-weight: 600;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		color: var(--text-faint);
	}

	.antenna-badge.present {
		background: var(--accent-soft);
		border-color: rgba(34, 197, 94, 0.35);
		color: #4ade80;
	}

	.actions-cell {
		display: flex;
		justify-content: flex-end;
		gap: 6px;
	}

	tr.selected {
		background: var(--bg-hover);
	}

	.link-btn {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		font-weight: 500;
		color: var(--text);
		cursor: pointer;
	}

	.link-btn:hover {
		color: var(--accent);
		text-decoration: underline;
	}

	.tags-panel {
		margin-top: 16px;
		padding: 16px;
	}

	.tags-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		margin-bottom: 12px;
	}

	.tags-header h3 {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
	}

	.tags-list {
		max-height: 320px;
		overflow-y: auto;
	}

	@media (max-width: 820px) {
		.page-header,
		.page-content {
			padding-left: 16px;
			padding-right: 16px;
		}
	}
</style>
