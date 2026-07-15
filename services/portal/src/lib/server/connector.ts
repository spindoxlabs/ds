/**
 * Server-side fetch wrappers for ds-connector API.
 * Always called from +page.server.ts load functions — never from the browser.
 */
import { env } from '$env/dynamic/private';
import { env as pubEnv } from '$env/dynamic/public';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

function connectorUrl(path: string): string {
	const base = env.CONNECTOR_URL ?? pubEnv.PUBLIC_CONNECTOR_URL ?? 'http://ds-connector:30001';
	return `${base}${path}`;
}

function identityRegistryUrl(): string {
	return env.IDENTITY_REGISTRY_URL ?? 'http://172.17.0.1:30005';
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

export function subjectFromAccessToken(accessToken: string | undefined): string {
	if (env.DEFAULT_SUBJECT_ID) return env.DEFAULT_SUBJECT_ID;
	if (!accessToken) return '';
	try {
		const payload = JSON.parse(Buffer.from(accessToken.split('.')[1], 'base64url').toString('utf-8')) as {
			preferred_username?: string;
			sub?: string;
			email?: string;
		};
		const candidates = [
			emailSubjectId(payload.email),
			emailSubjectId(payload.preferred_username),
			payload.preferred_username,
			payload.email,
			payload.sub,
		].filter((value): value is string => Boolean(value));
		return candidates.find((candidate) => Boolean(userVcForSubject(candidate))) ?? candidates[0] ?? '';
	} catch {
		return '';
	}
}

export function emailSubjectId(email: string | undefined): string {
	const normalized = email?.trim().toLowerCase() ?? '';
	if (!normalized || !normalized.includes('@')) return '';
	const digest = createHash('sha256').update(normalized).digest('hex').slice(0, 24);
	return `email-${digest}`;
}

export function userVcForSubject(subjectId: string): string {
	if (!subjectId) return '';
	const base = env.USER_CREDENTIALS_PATH ?? '/credentials/users';
	try {
		const vc = JSON.parse(readFileSync(join(base, subjectId, 'user-vc.json'), 'utf-8')) as {
			proof?: { jws?: string };
		};
		return vc.proof?.jws ?? '';
	} catch {
		return '';
	}
}

export function userVcRoleForSubject(subjectId: string): string | null {
	if (!subjectId) return null;
	const base = env.USER_CREDENTIALS_PATH ?? '/credentials/users';
	try {
		const vc = JSON.parse(readFileSync(join(base, subjectId, 'user-vc.json'), 'utf-8')) as {
			credentialSubject?: { role?: string };
		};
		return vc.credentialSubject?.role ?? null;
	} catch {
		return null;
	}
}

export function subjectCredentialHeaders(subjectId: string): Record<string, string> {
	return {
		'X-Subject-Id': subjectId,
		'X-User-VC': userVcForSubject(subjectId),
	};
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

export async function getMyConsents(token: string, subjectId: string): Promise<ConsentRequest[]> {
	return apiFetch<ConsentRequest[]>(
		connectorUrl('/consent/my'),
		{ headers: subjectCredentialHeaders(subjectId) },
		token,
	);
}

export async function getMyConsent(id: string, token: string, subjectId: string): Promise<ConsentRequest> {
	return apiFetch<ConsentRequest>(
		connectorUrl(`/consent/my/${id}`),
		{ headers: subjectCredentialHeaders(subjectId) },
		token,
	);
}

export async function approveConsent(id: string, token: string, subjectId: string): Promise<void> {
	return apiFetch<void>(
		connectorUrl(`/consent/my/${id}/approve`),
		{ method: 'POST', headers: subjectCredentialHeaders(subjectId) },
		token,
	);
}

export async function rejectConsent(id: string, token: string, subjectId: string): Promise<void> {
	return apiFetch<void>(
		connectorUrl(`/consent/my/${id}/reject`),
		{ method: 'POST', headers: subjectCredentialHeaders(subjectId) },
		token,
	);
}

export async function revokeConsent(id: string, token: string, subjectId: string): Promise<void> {
	return apiFetch<void>(
		connectorUrl(`/consent/my/${id}/revoke`),
		{ method: 'POST', headers: subjectCredentialHeaders(subjectId) },
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

export async function getMyDataShares(token: string, subjectId: string): Promise<DataShareDecision[]> {
	return apiFetch<DataShareDecision[]>(
		connectorUrl('/consent/my/shares'),
		{ headers: subjectCredentialHeaders(subjectId) },
		token,
	);
}

export async function setMyDataShare(
	token: string,
	subjectId: string,
	datasetId: string,
	enabled: boolean,
): Promise<DataShareDecision> {
	return apiFetch<DataShareDecision>(
		connectorUrl('/consent/my/shares'),
		{
			method: 'POST',
			headers: subjectCredentialHeaders(subjectId),
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
	medallion?: string;
	access_level?: string;
	tags?: string[];
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
			medallion: String(properties['ds:medallion'] ?? ''),
			access_level: String(properties['ds:accessLevel'] ?? ''),
			tags,
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
