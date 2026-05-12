<script lang="ts">
	export let datasetType = 'csv';
	export let size: 'sm' | 'md' = 'md';

	$: color = `var(--ds-${datasetType || 'csv'}, var(--da-accent))`;
</script>

<span class="icon {size}" style:--icon-color={color} aria-hidden="true">
	<span></span>
</span>

<style>
	.icon {
		inline-size: 36px;
		block-size: 44px;
		border: 1px solid var(--icon-color);
		border-radius: 6px;
		background: color-mix(in srgb, var(--icon-color) 12%, transparent);
		position: relative;
		display: inline-block;
		flex: 0 0 auto;
	}

	.icon.sm {
		inline-size: 24px;
		block-size: 30px;
		border-radius: 5px;
	}

	.icon span {
		position: absolute;
		inset-inline-end: -1px;
		inset-block-start: -1px;
		inline-size: 12px;
		block-size: 12px;
		border-inline-start: 1px solid var(--icon-color);
		border-block-end: 1px solid var(--icon-color);
		background: var(--da-panel);
		border-end-start-radius: 4px;
	}
</style>
