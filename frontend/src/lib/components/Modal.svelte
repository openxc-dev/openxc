<script>
	export let title = '';
	export let onClose = () => {};
	export let width = '480px';

	function handleKeydown(e) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="overlay" on:click={onClose} role="presentation">
	<div
		class="panel"
		style="max-width: {width}"
		on:click|stopPropagation
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<div class="panel-header">
			<h3>{title}</h3>
			<button class="close-btn" on:click={onClose} aria-label="Close">✕</button>
		</div>
		<div class="panel-body">
			<slot />
		</div>
	</div>
</div>

<style>
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

	.panel {
		background: var(--bg-card);
		border: 1px solid var(--border);
		border-radius: 12px;
		width: 100%;
		max-height: 90vh;
		overflow-y: auto;
		box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 20px;
		border-bottom: 1px solid var(--border);
		position: sticky;
		top: 0;
		background: var(--bg-card);
	}

	.close-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 16px;
		padding: 4px 8px;
		border-radius: 6px;
	}

	.close-btn:hover {
		background: var(--bg-hover);
		color: var(--text);
	}

	.panel-body {
		padding: 20px;
	}
</style>
