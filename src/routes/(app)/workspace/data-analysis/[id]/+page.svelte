<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import { page } from '$app/stores';
	import Chat from '$lib/components/chat/Chat.svelte';
	import CanvasFeed from '$lib/components/data-analysis/CanvasFeed.svelte';
	import DataAnalysisLayout from '$lib/components/data-analysis/DataAnalysisLayout.svelte';
	import DatasetPanel from '$lib/components/data-analysis/DatasetPanel.svelte';
	import { getChatById, updateChatById } from '$lib/apis/chats';
	import { getDataAnalysisDatasets, logDataAnalysisEvent } from '$lib/apis/data-analysis';
	import { datasets, datasetsState, selectedDatasetId } from '$lib/stores/data-analysis';

	const i18n =
		getContext<Writable<{ t: (key: string, options?: Record<string, unknown>) => string }>>('i18n');
	let chatId = '';
	$: chatId = $page.params.id ?? '';

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

	const loadChatMetadata = async () => {
		const chat = await getChatById(localStorage.token, chatId).catch(() => null);
		const metadata = chat?.chat?.metadata ?? {};
		activeDatasetId = metadata?.data_analysis?.selected_dataset_id ?? '';
		selectedDatasetId.set(activeDatasetId);
	};

	const persistMetadata = async () => {
		if (!chatId) return;
		const chat = await getChatById(localStorage.token, chatId).catch(() => null);
		if (!chat) return;
		await updateChatById(localStorage.token, chatId, {
			...(chat.chat ?? {}),
			metadata: extraMetadata
		});
	};

	const selectDataset = async (event: DatasetSelectedEvent) => {
		const previous = activeDatasetId;
		activeDatasetId = event.detail.datasetId;
		selectedDatasetId.set(activeDatasetId);
		await persistMetadata();
		logDataAnalysisEvent({
			event_type: 'dataset.selected',
			chat_id: chatId,
			dataset_id: activeDatasetId,
			payload: {
				dataset_id: activeDatasetId,
				prev_dataset_id: previous || null,
				from: event.detail.from
			}
		});
	};

	onMount(async () => {
		logDataAnalysisEvent({
			event_type: 'workspace.opened',
			chat_id: chatId,
			payload: { entry_path: 'sidebar-history' }
		});
		await loadChatMetadata();
		await loadDatasets();
	});
</script>

<DataAnalysisLayout>
	<DatasetPanel
		slot="left"
		{chatId}
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
				chat_id: chatId,
				message_id: e.detail.messageId,
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
		{#key chatId}
			<Chat
				chatIdProp={chatId}
				extraToolIds={['builtin:data-analysis']}
				{extraMetadata}
				chatRoutePrefix="/workspace/data-analysis"
				onHistoryChange={(history) => (historySnapshot = history)}
				onPromptSubmit={(prompt) =>
					logDataAnalysisEvent({
						event_type: 'prompt.submitted',
						chat_id: chatId,
						payload: {
							prompt_text: prompt,
							prompt_length: prompt.length,
							model: '',
							is_first_in_chat: messages.length === 0
						},
						dataset_id: activeDatasetId || undefined
					})}
				onStreamAbort={() =>
					logDataAnalysisEvent({
						event_type: 'stream.aborted',
						chat_id: chatId,
						payload: { chat_id: chatId, reason: 'user-cancel' }
					})}
			/>
		{/key}
	</div>
</DataAnalysisLayout>

<style>
	.chat-shell {
		block-size: 100%;
		overflow: hidden;
	}
</style>
