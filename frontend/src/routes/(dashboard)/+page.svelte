<script>
	import { meetsStore } from '$lib/stores';
</script>

<div class="empty-state" style="height: 100%;">
	{#if $meetsStore.length === 0}
		<h2>Welcome to OpenXC Timing</h2>
		<p>Create your first meet using the "New Meet" button in the sidebar.</p>
	{:else}
		<h2>Select a meet</h2>
		<p>Choose a meet from the sidebar, or create a new one.</p>
	{/if}
</div>
