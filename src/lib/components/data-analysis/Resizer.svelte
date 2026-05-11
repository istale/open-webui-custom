<script lang="ts">
	export let side: 'left' | 'right';
	export let onResize: (clientX: number) => void;

	let dragging = false;

	const stop = () => {
		dragging = false;
		document.body.style.cursor = '';
		document.body.style.userSelect = '';
		window.removeEventListener('mousemove', move);
		window.removeEventListener('mouseup', stop);
	};

	const move = (event: MouseEvent) => {
		if (dragging) onResize(event.clientX);
	};

	const start = () => {
		dragging = true;
		document.body.style.cursor = 'col-resize';
		document.body.style.userSelect = 'none';
		window.addEventListener('mousemove', move);
		window.addEventListener('mouseup', stop);
	};
</script>

<button
	type="button"
	class:dragging
	class="resizer"
	aria-label={`${side} panel resize handle`}
	on:mousedown={start}
>
	<span />
</button>

<style>
	.resizer {
		inline-size: 7px;
		border: 0;
		padding: 0;
		cursor: col-resize;
		background: transparent;
		display: grid;
		place-items: center;
	}

	.resizer span {
		inline-size: 2px;
		block-size: 100%;
		background: var(--da-border-strong);
		opacity: 0;
		transition: opacity 120ms ease;
	}

	.resizer:hover span,
	.resizer.dragging span {
		opacity: 0.55;
	}
</style>
