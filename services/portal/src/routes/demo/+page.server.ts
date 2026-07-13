import { env } from '$env/dynamic/private';
import type { Cookies } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

const CONSUMER_ID = env.DEMO_CONSUMER_ID ?? 'did:web:consumer.dataspaces.localhost';
const FALLBACK_SUBJECT_ID = env.DEMO_SUBJECT_ID ?? 'subject-001';
const DATASET_ID = env.DEMO_DATASET_ID ?? 'datasets.silver.meters_15m';
const COOKIE = 'ds_demo_consent_id';

type QueryResult = {
	dataset_name: string;
	count: number;
	rows: Array<Record<string, unknown>>;
	authorization: Record<string, unknown>;
};

type DemoState = {
	consentId?: string;
	consentStatus?: string;
	query?: QueryResult;
	error?: string;
	message?: string;
	consumerId: string;
	subjectId: string;
	datasetId: string;
	authenticated: boolean;
	userName?: string | null;
};

function connectorUrl(path: string): string {
	return `${env.CONNECTOR_URL ?? 'http://ds-connector:30001'}${path}`;
}

function datasetUrl(path: string): string {
	return `${env.DATASET_API_URL ?? env.CATALOGUE_URL ?? 'http://dataset-api:30002'}${path}`;
}

async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
	const headers = {
		'Content-Type': 'application/json',
		...(options.headers as Record<string, string> | undefined),
	};
	const response = await fetch(url, { ...options, headers });
	if (!response.ok) {
		const text = await response.text().catch(() => response.statusText);
		throw new Error(`${response.status}: ${text}`);
	}
	return response.json() as Promise<T>;
}

async function runQuery(): Promise<QueryResult> {
	const params = new URLSearchParams({
		dataset_name: DATASET_ID,
		consumer_id: CONSUMER_ID,
	});
	return apiFetch<QueryResult>(datasetUrl(`/query?${params}`));
}

async function consentStatus(subjectId: string): Promise<string> {
	const params = new URLSearchParams({
		consumer_id: CONSUMER_ID,
		dataset_id: DATASET_ID,
		subject_id: subjectId,
	});
	const body = await apiFetch<{ status: string }>(connectorUrl(`/consent/status?${params}`));
	return body.status;
}

function subjectFromAccessToken(accessToken: string | undefined): string {
	if (!accessToken) return FALLBACK_SUBJECT_ID;
	try {
		const payload = JSON.parse(Buffer.from(accessToken.split('.')[1], 'base64url').toString('utf-8')) as {
			dataspace_did?: string;
			preferred_username?: string;
			sub?: string;
		};
		return env.DEMO_SUBJECT_ID ?? payload.dataspace_did ?? payload.preferred_username ?? payload.sub ?? FALLBACK_SUBJECT_ID;
	} catch {
		return FALLBACK_SUBJECT_ID;
	}
}

async function stateFromCookies(
	cookies: Cookies,
	subjectId: string,
	authenticated: boolean,
	userName?: string | null,
): Promise<DemoState> {
	const consentId = cookies.get(COOKIE) ?? undefined;
	const [query, status] = await Promise.all([
		runQuery().catch((error: Error) => ({ error: error.message })),
		consentStatus(subjectId).catch(() => 'not_found'),
	]);

	return {
		consentId,
		consentStatus: status,
		query: 'error' in query ? undefined : query,
		error: 'error' in query ? query.error : undefined,
		consumerId: CONSUMER_ID,
		subjectId,
		datasetId: DATASET_ID,
		authenticated,
		userName,
	};
}

export const load: PageServerLoad = async ({ cookies, locals }) => {
	const session = await locals.auth();
	const subjectId = subjectFromAccessToken(session?.accessToken);
	return stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name);
};

export const actions: Actions = {
	request: async ({ cookies, locals }) => {
		const session = await locals.auth();
		const subjectId = subjectFromAccessToken(session?.accessToken);
		try {
			const body = await apiFetch<{ request_ids: string[] }>(connectorUrl('/consent/request'), {
				method: 'POST',
				body: JSON.stringify({
					consumer_id: CONSUMER_ID,
					dataset_id: DATASET_ID,
					subject_ids: [subjectId],
					purpose: ['demo'],
					message: 'CELINE dataspace demo consent request',
				}),
			});
			const consentId = body.request_ids[0];
			cookies.set(COOKIE, consentId, { path: '/demo', sameSite: 'lax' });
			return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), consentId, message: 'Consent request created.' };
		} catch (error) {
			return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), error: (error as Error).message };
		}
	},

	approve: async ({ cookies, request, locals }) => {
		const session = await locals.auth();
		const subjectId = subjectFromAccessToken(session?.accessToken);
		const form = await request.formData();
		const consentId = String(form.get('consentId') || cookies.get(COOKIE) || '');
		try {
			if (!consentId) throw new Error('Create a consent request first.');
			await apiFetch(connectorUrl(`/consent/my/${consentId}/approve`), {
				method: 'POST',
				headers: { 'X-Subject-Id': subjectId },
			});
			return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), consentId, message: 'Consent granted.' };
		} catch (error) {
			return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), consentId, error: (error as Error).message };
		}
	},

	revoke: async ({ cookies, request, locals }) => {
		const session = await locals.auth();
		const subjectId = subjectFromAccessToken(session?.accessToken);
		const form = await request.formData();
		const consentId = String(form.get('consentId') || cookies.get(COOKIE) || '');
		try {
			if (!consentId) throw new Error('Create and approve a consent request first.');
			await apiFetch(connectorUrl(`/consent/my/${consentId}/revoke`), {
				method: 'POST',
				headers: { 'X-Subject-Id': subjectId },
			});
			return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), consentId, message: 'Consent revoked.' };
		} catch (error) {
			return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), consentId, error: (error as Error).message };
		}
	},

	clear: async ({ cookies, locals }) => {
		const session = await locals.auth();
		const subjectId = subjectFromAccessToken(session?.accessToken);
		cookies.delete(COOKIE, { path: '/demo' });
		return { ...(await stateFromCookies(cookies, subjectId, Boolean(session?.user), session?.user?.name)), message: 'Demo state cleared.' };
	},
};
