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

export async function queryEvents(params: Record<string, string> = {}): Promise<AuditEntry[]> {
	const qs = new URLSearchParams(params).toString();
	const raw = await apiFetch<{ '@graph': AuditEntry[] }>(
		provUrl(`/prov/events${qs ? '?' + qs : ''}`),
	);
	return raw['@graph'] ?? [];
}

export async function getHealth(): Promise<{ status: string }> {
	return apiFetch<{ status: string }>(provUrl('/health'));
}
