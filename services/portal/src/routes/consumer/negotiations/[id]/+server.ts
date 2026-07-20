/**
 * GET /consumer/negotiations/[id] — poll negotiation state.
 * Returns { id, state, agreement_id | null, error | null }.
 */
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

export const GET: RequestHandler = async ({ params, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const connectorUrl = env.CONSUMER_CONNECTOR_URL ?? 'http://172.17.0.1:31001';

	const res = await fetch(`${connectorUrl}/consumer/negotiations/${params.id}`, {
		headers: {
			...(token ? { Authorization: `Bearer ${token}` } : {}),
		},
	});

	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw error(res.status, text);
	}
	const data = await res.json();
	return json({
		...data,
		agreement_id:
			data.agreement_id
			?? data.contract_agreement_id
			?? data.contractAgreementId
			?? null,
	});
};
