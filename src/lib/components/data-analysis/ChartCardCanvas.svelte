<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';

	export let card;
	export let highlighted = false;

	const i18n =
		getContext<Writable<{ t: (key: string, options?: Record<string, unknown>) => string }>>('i18n');
	let imageFailed = false;
</script>

<article id={`chart-${card.chartId}`} class:highlighted class="card">
	<header>
		<div>
			<h3>{card.title}</h3>
			<p>{card.datasetId}</p>
		</div>
		<span>{card.chartType}</span>
	</header>

	{#if imageFailed}
		<div class="image-fallback">{$i18n.t('Chart image unavailable')}</div>
	{:else}
		<img src={card.url} alt={card.title} loading="lazy" on:error={() => (imageFailed = true)} />
	{/if}

	<section class="caption">
		<div><strong>{$i18n.t('Fields')}</strong><span>{card.fields || '-'}</span></div>
		<div><strong>{$i18n.t('Method')}</strong><span>{card.method || '-'}</span></div>
		<div><strong>{$i18n.t('Notes')}</strong><span>{card.notes || '-'}</span></div>
	</section>
</article>

<style>
	.card {
		border: 1px solid var(--da-border);
		border-radius: var(--da-radius);
		background: var(--da-panel);
		box-shadow: var(--da-shadow);
		overflow: hidden;
		transition:
			border-color 140ms ease,
			box-shadow 140ms ease;
	}

	.card.highlighted {
		border-color: var(--da-accent);
		box-shadow: 0 0 0 3px var(--da-accent-soft);
	}

	header {
		min-block-size: 56px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 12px 14px;
		border-block-end: 1px solid var(--da-border);
	}

	h3,
	p {
		margin: 0;
	}

	h3 {
		font-size: 15px;
		font-weight: 700;
	}

	p {
		color: var(--da-text-muted);
		font-family: var(--da-font-mono);
		font-size: 11px;
	}

	header span {
		border-radius: 999px;
		background: var(--da-accent-soft);
		color: var(--da-accent);
		padding: 4px 8px;
		font-size: 11px;
		font-weight: 700;
	}

	img,
	.image-fallback {
		inline-size: 100%;
		aspect-ratio: 16 / 9;
		display: grid;
		place-items: center;
		background: var(--da-panel-muted);
		object-fit: contain;
	}

	.image-fallback {
		color: var(--da-error);
		font-size: 13px;
	}

	.caption {
		display: grid;
		gap: 8px;
		padding: 12px 14px;
		font-size: 12px;
	}

	.caption div {
		display: grid;
		grid-template-columns: 76px minmax(0, 1fr);
		gap: 8px;
	}

	.caption strong {
		color: var(--da-text-muted);
	}
</style>
