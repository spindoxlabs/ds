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
	subject: string;
	object: string;
}

export interface LineageGraph {
	'@context': string;
	root: string;
	depth: number;
	'@graph': Array<ProvNode | LineageEdge>;
}

export async function getLineage(
	iri: string,
	opts: { direction?: string; maxDepth?: number } = {},
): Promise<LineageGraph> {
	const params = new URLSearchParams();
	params.set('direction', opts.direction ?? 'both');
	params.set('max_depth', String(opts.maxDepth ?? 5));
	return apiFetch<LineageGraph>(
		provUrl(`/prov/lineage/${encodeURIComponent(iri)}?${params}`),
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
}

function stringValue(value: unknown): string {
	return typeof value === 'string' ? value : '';
}

function normalizeEvent(event: Record<string, unknown>): AuditEntry {
	const eventType = stringValue(event.event_type ?? event['@type']).replace(/^ds:/, '');
	const occurredAt = stringValue(event.occurred_at ?? event['ds:occurredAt']);
	return {
		id: stringValue(event.id ?? event['@id']).replace(/^urn:event:/, ''),
		event_type: eventType,
		occurred_at: occurredAt,
		agreement_id: stringValue(event.agreement_id ?? event['ds:agreementId']) || undefined,
		data_product_id: stringValue(event.data_product_id ?? event['ds:dataProductId']) || undefined,
		provider_did: stringValue(event.provider_did ?? event['ds:providerDid']) || undefined,
		consumer_did: stringValue(event.consumer_did ?? event['ds:consumerDid']) || undefined,
	};
}

export async function queryEvents(params: Record<string, string> = {}): Promise<AuditEntry[]> {
	const qs = new URLSearchParams(params).toString();
	const raw = await apiFetch<{ '@graph': Array<Record<string, unknown>> }>(
		provUrl(`/prov/events${qs ? '?' + qs : ''}`),
	);
	return (raw['@graph'] ?? []).map(normalizeEvent);
}

export async function getHealth(): Promise<{ status: string }> {
	return apiFetch<{ status: string }>(provUrl('/health'));
}
