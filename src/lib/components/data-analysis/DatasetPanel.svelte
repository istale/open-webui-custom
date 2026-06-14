<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import DatasetRow from './DatasetRow.svelte';
	import type { DatasetMeta } from '$lib/stores/data-analysis';

	export let chatId: string | null = null;
	export let selectedDatasetId = '';
	export let datasets: DatasetMeta[] = [];
	export let activeGroupFilters: string[] = [];
	export let loading = false;
	export let error: string | null = null;

	const i18n =
		getContext<Writable<{ t: (key: string, options?: Record<string, unknown>) => string }>>('i18n');
	const dispatch = createEventDispatcher();

	$: tags = Array.from(new Set(datasets.flatMap((dataset) => dataset.tags ?? []))).sort();
	$: filtered =
		activeGroupFilters.length === 0
			? datasets
			: datasets.filter((dataset) =>
					activeGroupFilters.every((tag) => dataset.tags?.includes(tag))
				);

	const toggleTag = (tag: string) => dispatch('toggle-group-filter', { tag });
</script>

<section class="panel" aria-busy={loading}>
	<header>
		<div>
			<h2>{$i18n.t('Data Analysis')}</h2>
			<p>{$i18n.t('Manufacturing datasets')}</p>
		</div>
		<button
			type="button"
			on:click={() => dispatch('refresh-datasets')}
			aria-label={$i18n.t('Refresh')}
		>
			↻
		</button>
	</header>

	<div class="chips" aria-label={$i18n.t('Dataset filters')}>
		{#each tags as tag}
			<button
				type="button"
				class:active={activeGroupFilters.includes(tag)}
				on:click={() => toggleTag(tag)}
			>
				{tag}
			</button>
		{/each}
		{#if activeGroupFilters.length > 0}
			<button type="button" on:click={() => dispatch('reset-filters')}>{$i18n.t('Reset')}</button>
		{/if}
	</div>

	<div class="list">
		{#if loading}
			<div class="state">{$i18n.t('Loading datasets...')}</div>
		{:else if error}
			<div class="state error">{error}</div>
		{:else if filtered.length === 0}
			<div class="state">{$i18n.t('No datasets found')}</div>
		{:else}
			{#each filtered as dataset (dataset.id)}
				<DatasetRow
					{dataset}
					selected={dataset.id === selectedDatasetId}
					on:click={() => dispatch('select-dataset', { datasetId: dataset.id, from: 'row' })}
				/>
			{/each}
		{/if}
	</div>

	<footer>
		<span>{chatId ? $i18n.t('Active analysis') : $i18n.t('New analysis')}</span>
		<span>{filtered.length} {$i18n.t('datasets')}</span>
	</footer>
</section>

<style>
	.panel {
		block-size: 100%;
		display: grid;
		grid-template-rows: auto auto minmax(0, 1fr) auto;
		gap: 12px;
		padding: 16px;
	}

	header,
	footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
	}

	h2 {
		margin: 0;
		font-size: 16px;
		font-weight: 700;
	}

	p,
	footer {
		margin: 0;
		color: var(--da-text-muted);
		font-size: 12px;
	}

	header button,
	.chips button {
		border: 1px solid var(--da-border);
		background: var(--da-panel);
		color: var(--da-text);
		border-radius: 999px;
		min-block-size: 30px;
		padding: 0 10px;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.chips button.active {
		background: var(--da-accent-soft);
		border-color: var(--da-accent);
		color: var(--da-accent);
	}

	.list {
		overflow: auto;
		display: grid;
		align-content: start;
		gap: 4px;
	}

	.state {
		border: 1px dashed var(--da-border);
		border-radius: var(--da-radius);
		color: var(--da-text-muted);
		padding: 16px;
		font-size: 13px;
	}

	.error {
		color: var(--da-error);
	}
</style>
