<script lang="ts">
	import { onMount } from 'svelte';
	import Resizer from './Resizer.svelte';
	import '$lib/styles/data-analysis-tokens.css';

	export let leftWidth = 300;
	export let rightWidth = 480;

	const minLeft = 220;
	const maxLeft = 560;
	const minRight = 340;
	const maxRight = 680;

	const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

	onMount(() => {
		const storedLeft = Number(localStorage.getItem('data-analysis.layout.leftWidth'));
		const storedRight = Number(localStorage.getItem('data-analysis.layout.rightWidth'));
		if (storedLeft) leftWidth = clamp(storedLeft, minLeft, maxLeft);
		if (storedRight) rightWidth = clamp(storedRight, minRight, maxRight);
	});

	const resizeLeft = (clientX: number) => {
		leftWidth = clamp(clientX, minLeft, maxLeft);
		localStorage.setItem('data-analysis.layout.leftWidth', String(leftWidth));
	};

	const resizeRight = (clientX: number) => {
		rightWidth = clamp(window.innerWidth - clientX, minRight, maxRight);
		localStorage.setItem('data-analysis.layout.rightWidth', String(rightWidth));
	};
</script>

<div
	class="da-layout"
	style:grid-template-columns={`${leftWidth}px 7px minmax(360px, 1fr) 7px ${rightWidth}px`}
>
	<aside class="panel left"><slot name="left" /></aside>
	<Resizer side="left" onResize={resizeLeft} />
	<main class="panel middle"><slot name="middle" /></main>
	<Resizer side="right" onResize={resizeRight} />
	<section class="panel right"><slot name="right" /></section>
</div>

<style>
	.da-layout {
		block-size: 100%;
		min-block-size: calc(100vh - 56px);
		display: grid;
		background: var(--da-bg);
		color: var(--da-text);
		overflow: hidden;
	}

	.panel {
		min-inline-size: 0;
		block-size: 100%;
		overflow: hidden;
		background: var(--da-panel);
		border-inline-end: 1px solid var(--da-border);
	}

	.middle {
		background: var(--da-bg);
	}

	.right {
		border-inline-end: 0;
	}

	@media (max-width: 980px) {
		.da-layout {
			display: flex;
			flex-direction: column;
			overflow: auto;
		}

		.panel {
			min-block-size: 420px;
			border-inline-end: 0;
			border-block-end: 1px solid var(--da-border);
		}

		:global(.resizer) {
			display: none;
		}
	}
</style>
