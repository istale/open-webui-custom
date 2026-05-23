import { writable } from 'svelte/store';

export type DatasetMeta = {
	id: string;
	name: string;
	description: string;
	row_count: number;
	column_count: number;
	updated_at: string;
	tags: string[];
};

export type DatasetState = {
	loading: boolean;
	error: string | null;
	lastFetched: number;
};

export const selectedDatasetId = writable('');
export const datasets = writable<DatasetMeta[] | null>(null);
export const datasetsState = writable<DatasetState>({ loading: false, error: null, lastFetched: 0 });

// chart.rendered must fire once per chart creation, not once per page view.
// An in-memory Set resets on reload, so a reloaded chat would re-log existing
// charts. Dedup on the globally-unique chart_id (uuid4) in localStorage —
// chat-scoped keys are unsafe because a chart created on the new-chat route
// (chatId still '') would re-log after the URL gains its real id on reload.
const CHARTED_KEY = 'da:charted';
export function markChartRenderedOnce(_chatId: string, chartId: string): boolean {
	if (!chartId) return false;
	try {
		const seen = new Set<string>(JSON.parse(localStorage.getItem(CHARTED_KEY) ?? '[]'));
		if (seen.has(chartId)) return false;
		seen.add(chartId);
		// Cap growth: keep only the most recent 500 ids.
		const trimmed = [...seen].slice(-500);
		localStorage.setItem(CHARTED_KEY, JSON.stringify(trimmed));
		return true;
	} catch {
		return true; // storage unavailable: fail open, log the event
	}
}

type Listener = (payload: any) => void;
const listeners = new Map<string, Set<Listener>>();

export const workspaceEvents = {
	on(event: string, fn: Listener) {
		if (!listeners.has(event)) listeners.set(event, new Set());
		listeners.get(event)?.add(fn);
		return () => listeners.get(event)?.delete(fn);
	},
	emit(event: string, payload: any) {
		listeners.get(event)?.forEach((fn) => fn(payload));
	}
};
