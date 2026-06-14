import { WEBUI_API_BASE_URL } from '$lib/constants';
import type { DatasetMeta } from '$lib/stores/data-analysis';

export type DataAnalysisEventPayload = {
	event_type: string;
	chat_id?: string;
	message_id?: string;
	payload: Record<string, unknown>;
	dataset_id?: string;
	chart_type?: string;
	duration_ms?: number;
	error_code?: string;
};

export const logDataAnalysisEvent = (event: DataAnalysisEventPayload): void => {
	fetch(`${WEBUI_API_BASE_URL}/data-analysis/events`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		credentials: 'include',
		body: JSON.stringify(event)
	}).catch((error) => {
		console.warn('[data-analysis:event-ledger] failed to log event', error);
	});
};

export const getDataAnalysisDatasets = async (
	token = '',
	tags: string[] = []
): Promise<DatasetMeta[]> => {
	const search = new URLSearchParams();
	if (tags.length > 0) search.set('tags', tags.join(','));

	const res = await fetch(`${WEBUI_API_BASE_URL}/data-analysis/datasets?${search.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		credentials: 'include'
	});

	if (!res.ok) {
		throw await res.json();
	}

	const json = await res.json();
	return json.items ?? [];
};
