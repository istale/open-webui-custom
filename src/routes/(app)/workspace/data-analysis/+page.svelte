<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import Chat from '$lib/components/chat/Chat.svelte';
	import CanvasFeed from '$lib/components/data-analysis/CanvasFeed.svelte';
	import DataAnalysisLayout from '$lib/components/data-analysis/DataAnalysisLayout.svelte';
	import DatasetPanel from '$lib/components/data-analysis/DatasetPanel.svelte';
	import { getDataAnalysisDatasets, logDataAnalysisEvent } from '$lib/apis/data-analysis';
	import { datasets, datasetsState, selectedDatasetId } from '$lib/stores/data-analysis';

	const i18n =
		getContext<Writable<{ t: (key: string, options?: Record<string, unknown>) => string }>>('i18n');
	let chatId = '';
	let activeDatasetId = '';
	let activeFilters: string[] = [];
	type HistorySnapshot = {
		messages: Record<string, any>;
		currentId: string | null;
	};

	type DatasetSelectedEvent = CustomEvent<{ datasetId: string; from?: string }>;

	let historySnapshot: HistorySnapshot = { messages: {}, currentId: null };
	let loggedCharts = new Set<string>();

	$: messages = Object.values(historySnapshot.messages ?? {});
	$: visibleDatasets = $datasets ?? [];
	$: extraMetadata = {
		workspace_type: 'data-analysis',
		schema_version: 1,
		data_analysis: { selected_dataset_id: activeDatasetId }
	};

	const loadDatasets = async () => {
		datasetsState.set({ loading: true, error: null, lastFetched: Date.now() });
		try {
			const items = await getDataAnalysisDatasets(localStorage.token, activeFilters);
			datasets.set(items);
			if (!activeDatasetId && items[0]) {
				activeDatasetId = items[0].id;
				selectedDatasetId.set(activeDatasetId);
			}
			datasetsState.set({ loading: false, error: null, lastFetched: Date.now() });
		} catch (error) {
			datasetsState.set({ loading: false, error: String(error), lastFetched: Date.now() });
		}
	};

	const selectDataset = (event: DatasetSelectedEvent) => {
		const previous = activeDatasetId;
		activeDatasetId = event.detail.datasetId;
		selectedDatasetId.set(activeDatasetId);
		logDataAnalysisEvent({
			event_type: 'dataset.selected',
			dataset_id: activeDatasetId,
			payload: {
				dataset_id: activeDatasetId,
				prev_dataset_id: previous || null,
				from: event.detail.from
			}
		});
	};

	onMount(() => {
		logDataAnalysisEvent({ event_type: 'workspace.opened', payload: { entry_path: 'sidebar' } });
		loadDatasets();
	});
</script>

<DataAnalysisLayout>
	<DatasetPanel
		slot="left"
		chatId={null}
		selectedDatasetId={activeDatasetId}
		datasets={visibleDatasets}
		activeGroupFilters={activeFilters}
		loading={$datasetsState.loading}
		error={$datasetsState.error}
		on:select-dataset={selectDataset}
		on:toggle-group-filter={(e) =>
			(activeFilters = activeFilters.includes(e.detail.tag)
				? activeFilters.filter((tag) => tag !== e.detail.tag)
				: [...activeFilters, e.detail.tag])}
		on:reset-filters={() => (activeFilters = [])}
		on:refresh-datasets={loadDatasets}
	/>

	<CanvasFeed
		slot="middle"
		{messages}
		on:chart-rendered={(e) => {
			if (loggedCharts.has(e.detail.chartId)) return;
			loggedCharts.add(e.detail.chartId);
			logDataAnalysisEvent({
				event_type: 'chart.rendered',
				chart_type: e.detail.chartType,
				payload: {
					chart_id: e.detail.chartId,
					chart_type: e.detail.chartType,
					displayed_in: 'canvas-card'
				}
			});
		}}
	/>

	<div slot="right" class="chat-shell" aria-label={$i18n.t('Data analysis chat')}>
		<Chat
			chatIdProp={chatId}
			extraToolIds={['builtin:data-analysis']}
			{extraMetadata}
			chatRoutePrefix="/workspace/data-analysis"
			onVerticalHistoryChange={(history) => (historySnapshot = history)}
			onPromptSubmit={(prompt) =>
				logDataAnalysisEvent({
					event_type: 'prompt.submitted',
					payload: {
						prompt_text: prompt,
						prompt_length: prompt.length,
						model: '',
						is_first_in_chat: !chatId
					},
					dataset_id: activeDatasetId || undefined
				})}
			onStreamAbort={() =>
				logDataAnalysisEvent({
					event_type: 'stream.aborted',
					payload: { chat_id: chatId || null, reason: 'user-cancel' }
				})}
		/>
	</div>
</DataAnalysisLayout>

<style>
	.chat-shell {
		block-size: 100%;
		overflow: hidden;
	}
</style>
