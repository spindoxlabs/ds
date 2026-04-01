/**
 * Server-side fetch wrappers for ds-connector API.
 * Always called from +page.server.ts load functions — never from the browser.
 */
import { env } from '$env/dynamic/private';
import { env as pubEnv } from '$env/dynamic/public';

function connectorUrl(path: string): string {
	const base = env.CONNECTOR_URL ?? pubEnv.PUBLIC_CONNECTOR_URL ?? 'http://ds-connector:30001';
	return `${base}${path}`;
}

async function apiFetch<T>(
	url: string,
	options: RequestInit = {},
	token?: string,
): Promise<T> {
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(options.headers as Record<string, string> ?? {}),
	};
	if (token) headers['Authorization'] = `Bearer ${token}`;

	const res = await fetch(url, { ...options, headers });
	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${url}: ${text}`);
	}
	if (res.status === 204) return undefined as T;
	return res.json() as Promise<T>;
}

// ── Consent ──────────────────────────────────────────────────────────────────

export interface ConsentRequest {
	id: string;
	subject_id: string;
	dataset_id: string;
	consumer_id: string;
	status: 'pending' | 'granted' | 'rejected' | 'revoked';
	purpose: string[] | null;
	message: string | null;
	created_at: string;
	updated_at: string;
}

export async function getMyConsents(token: string): Promise<ConsentRequest[]> {
	return apiFetch<ConsentRequest[]>(connectorUrl('/consent/my'), {}, token);
}

export async function getMyConsent(id: string, token: string): Promise<ConsentRequest> {
	return apiFetch<ConsentRequest>(connectorUrl(`/consent/my/${id}`), {}, token);
}

export async function approveConsent(id: string, token: string): Promise<void> {
	return apiFetch<void>(connectorUrl(`/consent/my/${id}/approve`), { method: 'POST' }, token);
}

export async function rejectConsent(id: string, token: string): Promise<void> {
	return apiFetch<void>(connectorUrl(`/consent/my/${id}/reject`), { method: 'POST' }, token);
}

export async function revokeConsent(id: string, token: string): Promise<void> {
	return apiFetch<void>(connectorUrl(`/consent/my/${id}/revoke`), { method: 'POST' }, token);
}

// ── Provider ─────────────────────────────────────────────────────────────────

export interface ProviderAsset {
	asset_id: string;
	name: string;
	description?: string;
	medallion?: string;
	access_level?: string;
	tags?: string[];
	edc_synced?: boolean;
}

export async function syncGovernance(token: string): Promise<{ synced: number }> {
	return apiFetch<{ synced: number }>(connectorUrl('/provider/sync'), { method: 'POST' }, token);
}

export async function listProviderAssets(token: string): Promise<ProviderAsset[]> {
	return apiFetch<ProviderAsset[]>(connectorUrl('/provider/assets'), {}, token);
}

export async function listProviderContracts(token: string): Promise<ContractAgreement[]> {
	return apiFetch<ContractAgreement[]>(connectorUrl('/provider/transfers'), {}, token);
}

export interface ContractAgreement {
	agreement_id: string;
	asset_id: string;
	provider_id: string;
	consumer_id: string;
	status: string;
	agreed_at?: string;
	terminated_at?: string;
}

// ── Consumer ─────────────────────────────────────────────────────────────────

export interface CatalogDataset {
	'@id': string;
	'@type': string;
	'dct:title'?: string;
	'dct:description'?: string;
	'dcat:theme'?: string | string[];
	'odrl:hasPolicy'?: OdrlPolicy | OdrlPolicy[];
	[key: string]: unknown;
}

export interface OdrlPolicy {
	'@id': string;
	'@type': string;
	'odrl:permission'?: OdrlRule[];
	'odrl:prohibition'?: OdrlRule[];
	'odrl:obligation'?: OdrlRule[];
	[key: string]: unknown;
}

export interface OdrlRule {
	'odrl:action'?: { '@id': string } | string;
	'odrl:constraint'?: OdrlConstraint | OdrlConstraint[];
	[key: string]: unknown;
}

export interface OdrlConstraint {
	'odrl:leftOperand'?: string | { '@id': string };
	'odrl:operator'?: string | { '@id': string };
	'odrl:rightOperand'?: string;
	[key: string]: unknown;
}

export async function fetchCatalog(
	providerDspUrl: string,
	token: string,
): Promise<CatalogDataset[]> {
	const body = { provider_dsp_url: providerDspUrl };
	const raw = await apiFetch<{ 'dcat:dataset'?: CatalogDataset[] }>(
		connectorUrl('/consumer/catalog'),
		{ method: 'POST', body: JSON.stringify(body) },
		token,
	);
	return raw?.['dcat:dataset'] ?? [];
}

export interface FlowRequest {
	provider_participant_id: string;
	asset_id: string;
}

export interface FlowResult {
	agreement_id: string;
	transfer_id: string;
	edr?: { endpoint: string; authorization: string };
}

export async function runFlow(req: FlowRequest, token: string): Promise<FlowResult> {
	return apiFetch<FlowResult>(
		connectorUrl('/consumer/flow'),
		{ method: 'POST', body: JSON.stringify(req) },
		token,
	);
}

export async function listNegotiations(token: string): Promise<unknown[]> {
	return apiFetch<unknown[]>(connectorUrl('/consumer/catalog'), {}, token);
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<{ status: string; version: string }> {
	return apiFetch<{ status: string; version: string }>(connectorUrl('/health'));
}
