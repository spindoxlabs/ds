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
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';

	const res = await fetch(`${connectorUrl}/consumer/negotiations/${params.id}`, {
		headers: {
			...(token ? { Authorization: `Bearer ${token}` } : {}),
		},
	});

	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw error(res.status, text);
	}
	return json(await res.json());
};
