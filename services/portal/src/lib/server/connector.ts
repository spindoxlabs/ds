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

export function subjectCredentialHeaders(subjectId: string, vcJws?: string | null): Record<string, string> {
	const headers: Record<string, string> = { 'X-Subject-Id': subjectId };
	if (vcJws) headers['X-User-VC'] = vcJws;
	return headers;
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
	requested_at: string;
	decided_at?: string | null;
	revoked_at?: string | null;
}

export async function getMyConsents(token: string, subjectId: string, vcJws?: string | null): Promise<ConsentRequest[]> {
	return apiFetch<ConsentRequest[]>(
		connectorUrl('/consent/my'),
		{ headers: subjectCredentialHeaders(subjectId, vcJws) },
		token,
	);
}

export async function getMyConsent(id: string, token: string, subjectId: string, vcJws?: string | null): Promise<ConsentRequest> {
	return apiFetch<ConsentRequest>(
		connectorUrl(`/consent/my/${id}`),
		{ headers: subjectCredentialHeaders(subjectId, vcJws) },
		token,
	);
}

export async function approveConsent(id: string, token: string, subjectId: string, vcJws?: string | null): Promise<void> {
	return apiFetch<void>(
		connectorUrl(`/consent/my/${id}/approve`),
		{ method: 'POST', headers: subjectCredentialHeaders(subjectId, vcJws) },
		token,
	);
}

export async function rejectConsent(id: string, token: string, subjectId: string, vcJws?: string | null): Promise<void> {
	return apiFetch<void>(
		connectorUrl(`/consent/my/${id}/reject`),
		{ method: 'POST', headers: subjectCredentialHeaders(subjectId, vcJws) },
		token,
	);
}

export async function revokeConsent(id: string, token: string, subjectId: string, vcJws?: string | null): Promise<void> {
	return apiFetch<void>(
		connectorUrl(`/consent/my/${id}/revoke`),
		{ method: 'POST', headers: subjectCredentialHeaders(subjectId, vcJws) },
		token,
	);
}

export interface OwnedDataset {
	name: string;
	asset_id: string;
	title?: string;
	requires_consent: boolean;
	subject_column?: string;
	sample_rows?: number;
	source?: string;
}

export type DataShareDecision = ConsentRequest;

export async function getMyDataShares(token: string, subjectId: string, vcJws?: string | null): Promise<DataShareDecision[]> {
	return apiFetch<DataShareDecision[]>(
		connectorUrl('/consent/my/shares'),
		{ headers: subjectCredentialHeaders(subjectId, vcJws) },
		token,
	);
}

export async function setMyDataShare(
	token: string,
	subjectId: string,
	datasetId: string,
	enabled: boolean,
	vcJws?: string | null,
): Promise<DataShareDecision> {
	return apiFetch<DataShareDecision>(
		connectorUrl('/consent/my/shares'),
		{
			method: 'POST',
			headers: subjectCredentialHeaders(subjectId, vcJws),
			body: JSON.stringify({
				dataset_id: datasetId,
				enabled,
				purpose: ['ds:purpose:EnergyBalancing', 'ds:purpose:GridMonitoring'],
			}),
		},
		token,
	);
}

// ── Provider ─────────────────────────────────────────────────────────────────

export interface ProviderAsset {
	asset_id: string;
	name: string;
	description?: string;
	access_level?: string;
	classification?: string;
	source_system?: string;
	tags?: string[];
	owner?: string;
	ownerDid?: string;
	edc_synced?: boolean;
}

export async function syncGovernance(token: string): Promise<{ synced: number }> {
	return apiFetch<{ synced: number }>(connectorUrl('/provider/sync'), { method: 'POST' }, token);
}

export async function listProviderAssets(token: string): Promise<ProviderAsset[]> {
	const assets = await apiFetch<Record<string, unknown>[]>(connectorUrl('/provider/assets'), {}, token);
	return assets.map((asset) => {
		const properties = (asset.properties ?? asset['edc:properties'] ?? {}) as Record<string, unknown>;
		const id = String(asset['@id'] ?? asset.id ?? properties.id ?? properties['edc:id'] ?? '');
		const tags = String(properties['ds:tags'] ?? '')
			.split(',')
			.map((tag) => tag.trim())
			.filter(Boolean);
		return {
			asset_id: id,
			name: String(properties.name ?? id),
			description: String(properties.description ?? ''),
			access_level: String(properties['ds:accessLevel'] ?? ''),
			classification: String(properties['ds:classification'] ?? ''),
			source_system: String(properties['ds:sourceSystem'] ?? ''),
			tags,
			owner: String(properties['ds:owner'] ?? ''),
			ownerDid: String(properties['ds:ownerDid'] ?? ''),
			edc_synced: true,
		};
	});
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

// ── Health ────────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<{ status: string; version: string }> {
	return apiFetch<{ status: string; version: string }>(connectorUrl('/health'));
}
