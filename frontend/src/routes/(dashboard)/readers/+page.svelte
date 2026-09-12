<script>
	import { onDestroy, onMount } from 'svelte';
	import { api } from '$lib/api';
	import { readersStore } from '$lib/stores';

	function readerModel(reader) {
		const parts = [reader.manufacturer, reader.product].filter(Boolean);
		return parts.length > 0 ? parts.join(' ') : null;
	}

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
		// connected_antennas/num_antennas are last-known values that stick
		// around in the DB after a disconnect, so without this check a
		// disconnected reader would still show its old antennas as present.
		// Forcing every slot dark while not connected is a secondary visual
		// cue (alongside the Status column) that the reader is offline.
		const isReaderConnected = reader.status === 'connected';
		return Array.from({ length: count }, (_, i) => {
			const id = i + 1;
			// connected_antennas is the real per-antenna "is something
			// actually plugged in" status — lit only for those specific
			// IDs. If the reader didn't report it (null), fall back to
			// treating every port up to num_antennas as lit, since that's
			// the best information available.
			const present =
				isReaderConnected && (connected ? connected.includes(id) : id <= (reader.num_antennas || 0));
			return { id, present };
		});
	}

	// Backed by a shared store (not local state) so that bulk actions
	// triggered elsewhere — the sidebar's Start all/Stop all buttons — are
	// reflected here too, without this page having to poll.
	$: readers = $readersStore;
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

	// --- Global tag-read stream: spans every reader, so an antenna badge is
	// keyed by "label:antennaId" rather than just antenna id (antenna 2 on
	// reader A and antenna 2 on reader B are unrelated). Fed by a live SSE
	// subscription (see events/server.py) rather than polling /api/tags, so
	// the main table's antenna badges react the instant a read is published
	// — not just while the detail panel is open, since the subscription
	// runs for the lifetime of the page regardless of that panel's state. ---
	const RECENT_MS = 1000; // "lit" window for a normal (non-test-mode) read
	const MAX_STORED_TAGS = 2000;
	let idCounter = 0;

	let showTagReads = true;
	let allTags = []; // accumulated, newest first
	let tagsError = '';
	let eventSource = null;
	let lastSeenMap = {}; // "label:antenna" -> ms epoch of most recent read

	let now = Date.now();
	let nowTickHandle = null;

	// Antenna Test Mode: normally an antenna is lit only if it produced a
	// read within the last second (a live "what's firing right now"
	// indicator). In test mode, every antenna (on any reader) that has seen
	// a read since the toggle was turned on stays lit — so an operator can
	// flip it on, walk a tag past each antenna in turn, then come back and
	// see which ones registered without needing to catch each one lighting
	// up in real time.
	let testMode = false;
	let testModeSeenAntennas = new Set();

	function antennaKey(label, antennaId) {
		return `${label}:${antennaId}`;
	}

	// Svelte only tracks variables actually referenced in a template
	// expression — calling a plain function that closes over other state
	// doesn't register as a dependency. Computing the lit set here, with
	// every input (testMode, testModeSeenAntennas, now, lastSeenMap)
	// referenced directly in this $: expression, makes the antenna badges
	// update correctly (including the live 1s decay, driven by `now`).
	$: litSet = testMode
		? testModeSeenAntennas
		: new Set(
				Object.entries(lastSeenMap)
					.filter(([, t]) => now - t < RECENT_MS)
					.map(([key]) => key)
			);

	function setTestMode(value) {
		testMode = value;
		if (testMode) testModeSeenAntennas = new Set();
	}

	async function refresh() {
		try {
			await readersStore.refresh();
			loadError = '';
		} catch (e) {
			loadError = e.message;
		} finally {
			loading = false;
		}
	}

	// The events service (events/server.py) publishes the same fields
	// tag_stream.py XADDs to the Valkey stream, JSON-encoded — but since
	// XADD requires string values, antenna/rssi/timestamp arrive as strings
	// here and need parsing, unlike /api/tags's already-typed response.
	function parseSseTag(raw) {
		idCounter += 1;
		return {
			id: idCounter,
			event_type: raw.event_type || '',
			tag: raw.tag || '',
			antenna: raw.antenna ? Number(raw.antenna) : null,
			rssi: raw.rssi ? Number(raw.rssi) : null,
			timestamp: raw.timestamp ? Number(raw.timestamp) : null,
			time: raw.time || null,
			label: raw.label || '',
			reader_id: raw.reader_id || ''
		};
	}

	function handleTagEvent(event) {
		let raw;
		try {
			raw = JSON.parse(event.data);
		} catch (e) {
			return; // malformed payload — ignore rather than break the stream
		}
		const t = parseSseTag(raw);

		if (t.label && t.antenna != null) {
			const key = antennaKey(t.label, t.antenna);
			// Use the numeric epoch field, not new Date(t.time) — a
			// timezone-less ISO string parses as *local* time in JS, not
			// UTC, which silently corrupts this by a browser-timezone-sized
			// offset.
			const ts = t.timestamp != null ? t.timestamp * 1000 : Date.now();
			if (!lastSeenMap[key] || ts > lastSeenMap[key]) lastSeenMap[key] = ts;
			lastSeenMap = { ...lastSeenMap };
			if (testMode) {
				testModeSeenAntennas.add(key);
				testModeSeenAntennas = testModeSeenAntennas;
			}
		}

		allTags = [t, ...allTags].slice(0, MAX_STORED_TAGS);
		tagsError = '';
	}

	function connectTagStream() {
		eventSource = new EventSource('/events/tag_read');
		eventSource.onopen = () => {
			tagsError = '';
		};
		eventSource.onmessage = handleTagEvent;
		eventSource.onerror = () => {
			// The browser retries the connection on its own; this just
			// reflects that to the operator while it does.
			tagsError = 'Live tag stream disconnected — reconnecting…';
		};
	}

	onMount(() => {
		refresh();
		connectTagStream();
		nowTickHandle = setInterval(() => (now = Date.now()), 300);
	});

	onDestroy(() => {
		if (eventSource) eventSource.close();
		if (nowTickHandle) clearInterval(nowTickHandle);
	});

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
			}
		} catch (e) {
			error = `${reader.label}: ${e.message}`;
		} finally {
			readingBusyLabel = null;
			await refresh();
		}
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
			<div class="header-actions">
				<label
					class="test-mode-toggle"
					title="Keep antenna badges lit once triggered, until turned off"
				>
					<input
						type="checkbox"
						checked={testMode}
						on:change={(e) => setTestMode(e.target.checked)}
					/>
					<span class="toggle-track"><span class="toggle-thumb"></span></span>
					Antenna Test Mode
				</label>
				<button class="btn btn-primary btn-sm" on:click={() => (creating = !creating)}>
					{creating ? 'Cancel' : '+ Add Reader'}
				</button>
			</div>
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
							<th>Model</th>
							<th>Serial Number</th>
							<th>Antennas</th>
							<th>Status</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{#each readers as reader (reader.id)}
							<tr>
								<td class="name-cell">{reader.label}</td>
								<td>{reader.ip_address}</td>
								<td>{readerModel(reader) ?? '—'}</td>
								<td>{reader.serial_number ?? '—'}</td>
								<td>
								<div class="antenna-badges">
									{#each antennaSlots(reader) as slot (slot.id)}
										<span
											class="antenna-badge"
											class:present={slot.present}
											class:lit={litSet.has(antennaKey(reader.label, slot.id))}
										>
											{slot.id}
										</span>
									{/each}
								</div>
							</td>
								<td>
									<div class="status-cell">
										<span class="badge" class:badge-accent={reader.status === 'connected'}>
											{reader.status}
										</span>
										{#if reader.reading}
											<span class="badge badge-accent">reading</span>
										{/if}
									</div>
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

		<div class="card tags-panel">
			<div class="tags-header">
				<h3>
					Tag reads
					<span class="count">({allTags.length})</span>
				</h3>
				<div class="tags-header-actions">
					<button class="btn btn-sm" disabled={allTags.length === 0} on:click={() => (allTags = [])}>
						Clear
					</button>
					<button class="btn btn-sm" on:click={() => (showTagReads = !showTagReads)}>
						{showTagReads ? 'Hide' : 'Show'}
					</button>
				</div>
			</div>

			{#if tagsError}<p class="error">{tagsError}</p>{/if}

			{#if showTagReads}
				{#if allTags.length === 0}
					<div class="empty-state">
						<p>No tag reads yet. Click Start on a reader to begin reading.</p>
					</div>
				{:else}
					<div class="tags-list scrollbar-thin">
						<table>
							<thead>
								<tr>
									<th>Reader</th>
									<th>Tag</th>
									<th>Antenna</th>
									<th>RSSI</th>
									<th>Time</th>
								</tr>
							</thead>
							<tbody>
								{#each allTags as t (t.id)}
									<tr>
										<td class="name-cell">{t.label || '—'}</td>
										<td>{t.tag}</td>
										<td>{t.antenna ?? '—'}</td>
										<td>{t.rssi ?? '—'}</td>
										<td>{formatTagTime(t.time)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{/if}
		</div>
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
		gap: 16px;
		flex-wrap: wrap;
	}

	.header-actions {
		display: flex;
		align-items: center;
		gap: 14px;
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

	.status-cell {
		display: flex;
		align-items: center;
		gap: 6px;
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

	/* Wins over .present when both apply — a "just triggered" antenna
	   during a live read or an antenna test walk. */
	.antenna-badge.lit {
		background: var(--accent);
		border-color: var(--accent);
		color: #06210f;
	}

	.actions-cell {
		display: flex;
		justify-content: flex-end;
		gap: 6px;
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

	.tags-header-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.test-mode-toggle {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12.5px;
		color: var(--text-muted);
		cursor: pointer;
		user-select: none;
	}

	.test-mode-toggle input {
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

	.test-mode-toggle input:checked + .toggle-track {
		background: var(--accent-soft);
		border-color: var(--accent);
	}

	.test-mode-toggle input:checked + .toggle-track .toggle-thumb {
		transform: translateX(12px);
		background: var(--accent);
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
