/**
 * GET /consumer/transfers/[id] — poll transfer state.
 * POST /consumer/transfers/[id] — query the EDR endpoint server-side.
 */
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { getConsumerSubjectId } from '$lib/server/auth';
import { subjectCredentialHeaders } from '$lib/server/connector';

function connectorUrl(): string {
	return env.CONNECTOR_URL ?? 'http://ds-connector:30001';
}

function toInternalDataUrl(endpoint: string): URL {
	const url = new URL(endpoint);
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';
	const internal = new URL(catalogueUrl);
	if ((url.hostname === 'localhost' || url.hostname === '127.0.0.1') && url.port === '30002') {
		url.protocol = internal.protocol;
		url.hostname = internal.hostname;
		url.port = internal.port;
	}
	return url;
}

async function connectorErrorMessage(res: Response): Promise<string> {
	const text = await res.text().catch(() => res.statusText);
	try {
		const body = JSON.parse(text);
		return String(body.detail ?? body.message ?? text);
	} catch {
		return text;
	}
}

export const GET: RequestHandler = async ({ params, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session ? getConsumerSubjectId(session) : '';

	const res = await fetch(`${connectorUrl()}/consumer/transfers/${params.id}`, {
		headers: {
			...subjectCredentialHeaders(subjectId, session?.userVcJws),
			...(token ? { Authorization: `Bearer ${token}` } : {}),
		},
	});

	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw error(res.status, text);
	}
	return json(await res.json());
};

export const POST: RequestHandler = async ({ params, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session ? getConsumerSubjectId(session) : '';
	const headers: Record<string, string> = {
		...subjectCredentialHeaders(subjectId, session?.userVcJws),
		...(token ? { Authorization: `Bearer ${token}` } : {}),
	};

	const [transferRes, edrRes] = await Promise.all([
		fetch(`${connectorUrl()}/consumer/transfers/${params.id}`, { headers }),
		fetch(`${connectorUrl()}/consumer/edr/${params.id}`, { headers }),
	]);

	if (!transferRes.ok) {
		throw error(transferRes.status, await connectorErrorMessage(transferRes));
	}
	if (!edrRes.ok) {
		throw error(edrRes.status, await connectorErrorMessage(edrRes));
	}

	const transfer = await transferRes.json();
	const edr = await edrRes.json();
	const endpoint = String(edr.endpoint ?? '');
	if (!endpoint) {
		throw error(404, 'EDR endpoint not available for this transfer');
	}

	const queryUrl = toInternalDataUrl(endpoint);
	const consumerId = env.CONSUMER_PARTICIPANT_DID ?? 'did:web:consumer.dataspaces.test';
	const agreementId =
		transfer.contractId
		?? transfer.contract_agreement_id
		?? transfer.contractAgreementId
		?? transfer.contract_agreement_id;

	if (!queryUrl.searchParams.has('consumer_id')) {
		queryUrl.searchParams.set('consumer_id', consumerId);
	}
	if (agreementId && !queryUrl.searchParams.has('agreement_id')) {
		queryUrl.searchParams.set('agreement_id', String(agreementId));
	}
	if (!queryUrl.searchParams.has('transfer_id')) {
		queryUrl.searchParams.set('transfer_id', params.id);
	}

	const dataRes = await fetch(queryUrl, {
		headers: {
			...(edr.authorization ? { Authorization: String(edr.authorization) } : {}),
		},
	});

	if (!dataRes.ok) {
		throw error(dataRes.status, await connectorErrorMessage(dataRes));
	}
	return json(await dataRes.json());
};
