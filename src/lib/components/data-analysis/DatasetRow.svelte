<script lang="ts">
	import DatasetIcon from './DatasetIcon.svelte';
	import { formatCount } from './scroll-utils';
	import type { DatasetMeta } from '$lib/stores/data-analysis';

	export let dataset: DatasetMeta;
	export let groupColor = 'var(--da-accent)';
	export let selected = false;
</script>

<button class:selected type="button" class="row" style:--group-color={groupColor} on:click>
	<DatasetIcon datasetType={dataset.tags?.includes('quality') ? 'sqlite' : 'csv'} size="sm" />
	<span class="main">
		<span class="name">{dataset.name}</span>
		<span class="description">{dataset.description}</span>
	</span>
	<span class="meta">
		<span>{formatCount(dataset.row_count)}</span>
		<span>{new Date(dataset.updated_at).toLocaleDateString()}</span>
	</span>
</button>

<style>
	.row {
		inline-size: 100%;
		min-block-size: 64px;
		border: 1px solid transparent;
		border-radius: var(--da-radius);
		background: transparent;
		color: var(--da-text);
		display: grid;
		grid-template-columns: 28px minmax(0, 1fr) auto;
		align-items: center;
		gap: 10px;
		padding: 8px;
		text-align: start;
	}

	.row:hover,
	.row.selected {
		background: var(--da-panel-muted);
		border-color: var(--da-border);
	}

	.row.selected {
		box-shadow: inset 3px 0 0 var(--group-color);
	}

	.main {
		min-inline-size: 0;
		display: grid;
		gap: 3px;
	}

	.name,
	.description {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.name {
		font-size: 13px;
		font-weight: 650;
	}

	.description,
	.meta {
		color: var(--da-text-muted);
		font-size: 11px;
	}

	.meta {
		font-family: var(--da-font-mono);
		display: grid;
		justify-items: end;
		gap: 4px;
	}
</style>
