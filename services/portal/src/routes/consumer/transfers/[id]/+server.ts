/**
 * GET /consumer/transfers/[id] — poll transfer state.
 * POST /consumer/transfers/[id] — query the EDR endpoint server-side.
 */
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { requireConsumerApi } from '$lib/server/auth';
import { subjectCredentialHeaders } from '$lib/server/connector';

function connectorUrl(): string {
	return env.CONSUMER_CONNECTOR_URL ?? 'http://172.17.0.1:31001';
}

function toInternalDataUrl(endpoint: string): URL {
	const url = new URL(endpoint);
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
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
	const { token, subjectId, vcJws } = await requireConsumerApi({ locals });

	const res = await fetch(`${connectorUrl()}/consumer/transfers/${params.id}`, {
		headers: {
			...subjectCredentialHeaders(subjectId, vcJws),
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
	const { token, subjectId, vcJws } = await requireConsumerApi({ locals });
	const headers: Record<string, string> = {
		...subjectCredentialHeaders(subjectId, vcJws),
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
	// The query names the dataset, the way the real dataset-api resolves it from
	// SQL. It is never a parameter beside the agreement: two sources for "which
	// dataset" is two chances for them to disagree.
	const assetId = transfer.assetId ?? transfer.asset_id ?? edr.asset_id ?? '';
	const agreementId =
		edr.agreement_id
		?? transfer.contractId
		?? transfer.contract_agreement_id
		?? transfer.contractAgreementId;

	// The exchange identifiers travel as headers, never as query parameters.
	// The data plane decides nothing from them on its own — it authenticates the
	// EDR token and asks ds, which refuses an agreement that is not this
	// consumer's and a purpose the agreement does not permit. `purpose` is the
	// one declared when access was requested, supplied by the connector so the
	// portal cannot quietly query under a different one.
	const purposes: string[] = Array.isArray(edr.purpose) ? edr.purpose : [];
	const dataRes = await fetch(queryUrl, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...(edr.authorization ? { Authorization: String(edr.authorization) } : {}),
			...(agreementId ? { 'Edc-Contract-Agreement-Id': String(agreementId) } : {}),
			'Edc-Transfer-Process-Id': params.id,
			...(purposes.length ? { 'Edc-Purpose': purposes.join(',') } : {}),
		},
		body: JSON.stringify({ sql: `SELECT * FROM ${String(assetId)}`, limit: 100 }),
	});

	if (!dataRes.ok) {
		throw error(dataRes.status, await connectorErrorMessage(dataRes));
	}
	return json(await dataRes.json());
};
