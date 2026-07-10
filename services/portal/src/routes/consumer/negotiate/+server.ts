/**
 * POST /consumer/negotiate — starts a contract negotiation asynchronously.
 * Returns { negotiation_id } immediately (202).
 */
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { consumerSubjectFromAccessToken } from '$lib/server/auth';
import { subjectCredentialHeaders } from '$lib/server/connector';

async function connectorErrorMessage(res: Response): Promise<string> {
	const text = await res.text().catch(() => res.statusText);
	try {
		const body = JSON.parse(text);
		return String(body.detail ?? body.message ?? text);
	} catch {
		return text;
	}
}

export const POST: RequestHandler = async ({ request, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = consumerSubjectFromAccessToken(token);
	const body = await request.json();
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const payload = {
		...body,
		counter_party_address:
			body.counter_party_address
			?? body.counterPartyAddress
			?? env.CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS
			?? 'http://edc-provider:19194/protocol/2025-1',
		offer_id: body.offer_id ?? body.offerId ?? body.asset_id,
		assigner:
			body.assigner
			?? body.provider_participant_id?.['@id']
			?? (typeof body.provider_participant_id === 'string' ? body.provider_participant_id : undefined)
			?? env.CONSUMER_DEFAULT_ASSIGNER
			?? 'did:web:provider.dataspaces.test',
	};

	const res = await fetch(`${connectorUrl}/consumer/negotiate`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...subjectCredentialHeaders(subjectId),
			...(token ? { Authorization: `Bearer ${token}` } : {}),
		},
		body: JSON.stringify(payload),
	});

	if (!res.ok) {
		throw error(res.status, await connectorErrorMessage(res));
	}
	const data = await res.json();
	return json(data, { status: 202 });
};
