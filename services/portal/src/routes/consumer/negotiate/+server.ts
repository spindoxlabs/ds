/**
 * POST /consumer/negotiate — starts a contract negotiation asynchronously.
 * Returns { negotiation_id } immediately (202).
 */
import { json, error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

export const POST: RequestHandler = async ({ request, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const body = await request.json();
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';

	const res = await fetch(`${connectorUrl}/consumer/negotiate`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...(token ? { Authorization: `Bearer ${token}` } : {}),
		},
		body: JSON.stringify(body),
	});

	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw error(res.status, text);
	}
	const data = await res.json();
	return json(data, { status: 202 });
};
