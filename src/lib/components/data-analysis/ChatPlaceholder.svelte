<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import { workspaceEvents } from '$lib/stores/data-analysis';

	export let attachmentId: string;
	export let title: string;
	export let chartType: string;

	const i18n =
		getContext<Writable<{ t: (key: string, options?: Record<string, unknown>) => string }>>('i18n');
</script>

<button
	type="button"
	class="placeholder"
	on:click={() => workspaceEvents.emit('focusCanvasCard', { attachmentId })}
>
	<span>
		<strong>{title}</strong>
		<small>{chartType}</small>
	</span>
	<em>{$i18n.t('Locate')}</em>
</button>

<style>
	.placeholder {
		inline-size: 100%;
		border: 1px solid var(--da-border);
		border-radius: var(--da-radius);
		background: var(--da-accent-soft);
		color: var(--da-text);
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding: 10px 12px;
		text-align: start;
	}

	span {
		min-inline-size: 0;
		display: grid;
		gap: 2px;
	}

	strong,
	small {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	strong {
		font-size: 13px;
	}

	small,
	em {
		color: var(--da-text-muted);
		font-size: 11px;
		font-style: normal;
	}
</style>
