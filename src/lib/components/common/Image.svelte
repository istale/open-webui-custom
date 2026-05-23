<script lang="ts">
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { safeImageUrl } from '$lib/utils/safeImageUrl';

	import { settings } from '$lib/stores';
	import ImagePreview from './ImagePreview.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { getContext, onDestroy } from 'svelte';

	export let src = '';
	export let alt = '';

	export let className = ` w-full ${($settings?.highContrastMode ?? false) ? '' : 'outline-hidden focus:outline-hidden'}`;

	export let imageClassName = 'rounded-lg';

	export let dismissible = false;
	export let onDismiss = () => {};

	const i18n = getContext('i18n');

	let _src = '';
	// [core-touch] Data-analysis chart PNGs are bearer-protected, so a plain <img>
	// (which cannot send the Authorization header) 401s. For those URLs only,
	// fetch with the token into a blob object URL; all other images are untouched.
	let blobUrl = '';
	let blobLoadedFor = '';
	const isDataAnalysisChart = (url: string) => /\/api\/v1\/data-analysis\/charts\//.test(url);

	const resolveSrc = async (rawSrc: string) => {
		const resolved = rawSrc.startsWith('/') ? `${WEBUI_BASE_URL}${rawSrc}` : rawSrc;
		if (!resolved || !isDataAnalysisChart(resolved)) {
			_src = safeImageUrl(resolved);
			return;
		}
		if (blobLoadedFor === resolved && blobUrl) {
			_src = blobUrl;
			return;
		}
		blobLoadedFor = resolved;
		try {
			const res = await fetch(resolved, {
				headers: { authorization: `Bearer ${localStorage.token}` }
			});
			if (!res.ok) throw new Error(String(res.status));
			if (blobUrl) URL.revokeObjectURL(blobUrl);
			blobUrl = URL.createObjectURL(await res.blob());
			_src = blobUrl;
		} catch {
			_src = safeImageUrl(resolved);
		}
	};

	$: resolveSrc(src);

	onDestroy(() => {
		if (blobUrl) URL.revokeObjectURL(blobUrl);
	});

	let showImagePreview = false;
</script>

<ImagePreview bind:show={showImagePreview} src={_src} {alt} />

<div class=" relative group w-fit flex items-center">
	<button
		class={className}
		on:click={() => {
			showImagePreview = true;
		}}
		aria-label={$i18n.t('Show image preview')}
		type="button"
	>
		<img src={_src} {alt} class={imageClassName} draggable="false" data-cy="image" />
	</button>

	{#if dismissible}
		<div class=" absolute -top-1 -right-1">
			<button
				aria-label={$i18n.t('Remove image')}
				class=" bg-white text-black border border-white rounded-full group-hover:visible invisible transition"
				type="button"
				on:click={() => {
					onDismiss();
				}}
			>
				<XMark className={'size-4'} />
			</button>
		</div>
	{/if}
</div>
