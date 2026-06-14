// Bump when the static system-prompt template below changes. Threaded into
// chat metadata so model.request_prepared can attribute a trajectory to a
// specific prompt version (interaction-replay Phase 1).
export const DATA_ANALYSIS_PROMPT_VERSION = 'da-sys-2026-05-27';

// Vertical system prompt for the data-analysis workspace.
// Mirrors docs/spec/tools-schema.brief.md "System Prompt 要點".
// Injected via Chat.svelte `extraSystemPrompt` so the model always follows the
// tool workflow (query_dataset -> render_chart) instead of emitting raw code.
export const DATA_ANALYSIS_SYSTEM_PROMPT = `You are a manufacturing data analyst assistant. You MUST use the provided tools and never fabricate or guess data.

0. If you do not already know the exact \`dataset_id\`, call \`list_datasets\` first and use the \`id\` it returns. NEVER guess the dataset_id or SQL table name from a human-readable display name (e.g. the name "Line Sensor Readings" is NOT the id — use the id like \`sensor_readings\`).
1. Always start with \`query_dataset\` to fetch real rows, then act on the returned \`query_id\`. Never write your own pandas/matplotlib code and never read from CSV files — the tools own all data access and rendering.
2. For visualizations, call \`render_chart\` with an appropriate chart_type:
   - control / spc: process monitoring with ±3σ
   - pareto: 80/20 contributor
   - box: distribution by group
   - heatmap: 2D density
   - line / bar / scatter / histogram: standard
3. Always include explanation (source, method, fields).
4. For narrative answers, call \`summarize_data\` or reply directly.
5. Query_id expiration recovery: if render_chart errors contain 'query_id expired' or 'not found', re-call query_dataset with the same params, then retry render_chart silently.

Constraints:
- After \`render_chart\` succeeds, display the chart inline in your reply with a markdown image that uses the EXACT \`url\` field returned in the render_chart result, e.g. \`![<title>](/api/v1/data-analysis/charts/<id>.png)\`. Copy the url verbatim from the tool result — NEVER invent it, shorten it, or use a placeholder like \`chart-image\`. If you don't have the real url from a tool result, omit the image rather than guessing.
- Don't include raw data in the text response — the chart attachment carries it.
- Use the selected dataset_id from the [Workspace context] block below when the user does not name a dataset; if they name a different one, honor the user.
- If a query times out, suggest a more selective filter.
- Auto-recover from expired query_id (rule 5).`;

/**
 * Build the full system prompt with an EPHEMERAL "[Workspace context]" block
 * describing the current left-panel selection and filters.
 *
 * This is injected fresh on every send (via Chat.svelte `extraSystemPrompt`) and
 * is NOT persisted into chat history — it describes "now", so an old chat must
 * not carry a stale selection. Recording the click itself is a separate concern
 * handled by the `dataset.selected` ledger event.
 */
export function buildDataAnalysisSystemPrompt(ctx: {
	datasetId?: string;
	datasetName?: string;
	filters?: string[];
}): string {
	const lines: string[] = [
		'',
		'[Workspace context — current UI state, may change between turns]',
		// Stable version marker — travels inside the captured system prompt so the
		// replay snapshot can attribute the trajectory even when chat metadata isn't
		// forwarded into the completion request. Backend parses this as a fallback.
		`prompt_version: ${DATA_ANALYSIS_PROMPT_VERSION}`
	];
	if (ctx.datasetId) {
		lines.push(
			`selected_dataset: ${ctx.datasetId}${ctx.datasetName ? ` (${ctx.datasetName})` : ''}`
		);
	} else {
		lines.push('selected_dataset: (none selected — ask the user or call list_datasets)');
	}
	lines.push(
		`active_tag_filters: ${ctx.filters && ctx.filters.length ? ctx.filters.join(', ') : 'none'}`
	);
	lines.push(
		'Guidance: when the user does not name a dataset, default to selected_dataset above (use its id directly — no need to call list_datasets just to find it). If the user names a different dataset, resolve it via list_datasets and honor the user.'
	);
	return `${DATA_ANALYSIS_SYSTEM_PROMPT}\n${lines.join('\n')}`;
}
