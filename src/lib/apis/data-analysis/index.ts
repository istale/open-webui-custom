import { WEBUI_API_BASE_URL } from '$lib/constants';
import type { DatasetMeta } from '$lib/stores/data-analysis';
export { logDataAnalysisEvent } from './events';
export type { DataAnalysisEventPayload } from './events';

export const getDataAnalysisDatasets = async (token = '', tags: string[] = []): Promise<DatasetMeta[]> => {
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
