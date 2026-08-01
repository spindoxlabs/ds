/**
 * Server-side fetch wrappers for ds-provenance API.
 */
import { env } from '$env/dynamic/private';
import { env as pubEnv } from '$env/dynamic/public';

function provUrl(path: string): string {
	const base = env.PROVENANCE_URL ?? pubEnv.PUBLIC_PROVENANCE_URL ?? 'http://ds-provenance:30000';
	return `${base}${path}`;
}

async function apiFetch<T>(url: string, options: RequestInit = {}, token?: string): Promise<T> {
	const headers: Record<string, string> = {
		Accept: 'application/ld+json',
		...(options.headers as Record<string, string> ?? {}),
	};
	if (token) headers['Authorization'] = `Bearer ${token}`;
	const res = await fetch(url, { ...options, headers });
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${url}: ${text}`);
	}
	return res.json() as Promise<T>;
}

export interface ProvNode {
	'@id': string;
	'@type': string;
	'prov:label'?: string;
	'prov:startedAtTime'?: string;
	'prov:endedAtTime'?: string;
	[key: string]: unknown;
}

export interface LineageEdge {
	'@id': string;
	'@type': string;
	/** Endpoint keys as the provenance service emits them (JSON-LD qualified-relation properties). */
	'prov:entity': string;
	'prov:activity': string;
}

export interface LineageGraph {
	'@context': string;
	root: string;
	depth: number;
	'@graph': Array<ProvNode | LineageEdge>;
}

export interface GraphNode {
	id: string;
	label: string;
	type: string;
}

export interface GraphEdge {
	id: string;
	source: string;
	target: string;
	label: string;
}

/**
 * Split a lineage `@graph` into nodes and edges for the graph view.
 *
 * An edge is recognised by the keys the provenance service actually emits —
 * `prov:entity` / `prov:activity` (`jsonld_service.relation_to_jsonld`) — not
 * `subject` / `object`, which nothing emits. Reading the wrong keys made every
 * edge fall through to the node branch, so the graph rendered every node and
 * **zero edges**. Kept pure so the classification is unit-tested without a
 * running provenance store.
 */
export function classifyLineageGraph(
	graph: Array<Record<string, unknown>>,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
	const nodes: GraphNode[] = [];
	const edges: GraphEdge[] = [];

	const lastSegment = (type: unknown): string => {
		const first = Array.isArray(type) ? type[0] : type;
		return String(first ?? '').split(':').pop() ?? '';
	};

	for (const item of graph) {
		const entity = item['prov:entity'];
		const activity = item['prov:activity'];
		if (typeof entity === 'string' && typeof activity === 'string') {
			edges.push({
				id: String(item['@id']),
				source: entity,
				target: activity,
				label: lastSegment(item['@type']),
			});
		} else {
			const id = String(item['@id']);
			nodes.push({
				id,
				label: String(item['prov:label'] ?? id.split('/').pop() ?? id),
				type: lastSegment(item['@type']) || 'Entity',
			});
		}
	}

	return { nodes, edges };
}

export async function getLineage(
	iri: string,
	opts: { direction?: string; maxDepth?: number } = {},
	token?: string,
): Promise<LineageGraph> {
	const params = new URLSearchParams();
	params.set('direction', opts.direction ?? 'both');
	params.set('max_depth', String(opts.maxDepth ?? 5));
	return apiFetch<LineageGraph>(
		provUrl(`/prov/lineage/${encodeURIComponent(iri)}?${params}`),
		{},
		token,
	);
}

export interface AuditEntry {
	id: string;
	event_type: string;
	occurred_at: string;
	agreement_id?: string;
	data_product_id?: string;
	provider_did?: string;
	consumer_did?: string;
	subject_id?: string;
	/**
	 * Every other field the event declared, keyed by its plain name
	 * (`consent_snapshot_hash`, `purpose`, `columns`, …).
	 *
	 * The previous client kept only the four shared columns, so a `DataDisclosed`
	 * arrived with its recipient, purposes and column names discarded before any
	 * page could render them. An event type is a shape we do not know ahead of
	 * time — carrying the rest verbatim is what lets a new one appear without a
	 * change here.
	 */
	detail: Record<string, unknown>;
}

export interface EventPage {
	events: AuditEntry[];
	total: number;
	limit: number;
	offset: number;
}

export interface EventQuery {
	event_type?: string[];
	subject_id?: string;
	dataset_id?: string;
	consumer_did?: string;
	provider_did?: string;
	agreement_id?: string;
	occurred_after?: string;
	occurred_before?: string;
	limit?: number;
	offset?: number;
}

function stringValue(value: unknown): string {
	return typeof value === 'string' ? value : '';
}

/** `ds:consentSnapshotHash` → `consent_snapshot_hash`. */
function plainKey(key: string): string {
	return key
		.replace(/^ds:/, '')
		.replace(/([a-z0-9])([A-Z])/g, '$1_$2')
		.toLowerCase();
}

const KNOWN_KEYS = new Set([
	'id',
	'event_type',
	'occurred_at',
	'agreement_id',
	'data_product_id',
	'provider_did',
	'consumer_did',
	'subject_id',
]);

function normalizeEvent(event: Record<string, unknown>): AuditEntry {
	const flat: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(event)) {
		if (key === '@id' || key === '@type') continue;
		flat[plainKey(key)] = value;
	}

	const detail: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(flat)) {
		if (!KNOWN_KEYS.has(key)) detail[key] = value;
	}

	return {
		id: stringValue(event.id ?? event['@id']).replace(/^urn:event:/, ''),
		event_type: stringValue(event.event_type ?? event['@type']).replace(/^ds:/, ''),
		occurred_at: stringValue(flat.occurred_at),
		agreement_id: stringValue(flat.agreement_id) || undefined,
		data_product_id: stringValue(flat.data_product_id) || undefined,
		provider_did: stringValue(flat.provider_did) || undefined,
		consumer_did: stringValue(flat.consumer_did) || undefined,
		subject_id: stringValue(flat.subject_id) || undefined,
		detail,
	};
}

function toSearchParams(query: EventQuery): URLSearchParams {
	const params = new URLSearchParams();
	for (const [key, value] of Object.entries(query)) {
		if (value === undefined || value === null || value === '') continue;
		// `event_type` is repeatable server-side — one key per value, not a join.
		if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)));
		else params.set(key, String(value));
	}
	return params;
}

function toPage(
	raw: Record<string, unknown>,
	fallbackLimit: number,
	fallbackOffset: number,
): EventPage {
	const graph = (raw['@graph'] ?? []) as Array<Record<string, unknown>>;
	return {
		events: graph.map(normalizeEvent),
		total: Number(raw['hydra:totalItems'] ?? graph.length),
		limit: Number(raw['hydra:limit'] ?? fallbackLimit),
		offset: Number(raw['hydra:offset'] ?? fallbackOffset),
	};
}

/** The operator/participant view — everything this participant recorded. */
export async function queryEvents(query: EventQuery = {}, token?: string): Promise<EventPage> {
	const params = toSearchParams(query);
	const raw = await apiFetch<Record<string, unknown>>(
		provUrl(`/prov/events${params.size ? '?' + params : ''}`),
		{},
		token,
	);
	return toPage(raw, query.limit ?? 50, query.offset ?? 0);
}

/**
 * A data subject's own history.
 *
 * Authenticated by the subject's verifiable credential, not by a scope — and the
 * subject is taken from that credential server-side, so there is deliberately no
 * `subject_id` to pass here.
 */
export async function queryMyEvents(
	query: Omit<EventQuery, 'subject_id' | 'consumer_did' | 'provider_did' | 'agreement_id'>,
	subjectId: string,
	vcJws?: string | null,
): Promise<EventPage> {
	const params = toSearchParams(query);
	const headers: Record<string, string> = { 'X-Subject-Id': subjectId };
	if (vcJws) headers['X-User-VC'] = vcJws;
	const raw = await apiFetch<Record<string, unknown>>(
		provUrl(`/prov/my/events${params.size ? '?' + params : ''}`),
		{ headers },
	);
	return toPage(raw, query.limit ?? 50, query.offset ?? 0);
}
