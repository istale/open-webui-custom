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
