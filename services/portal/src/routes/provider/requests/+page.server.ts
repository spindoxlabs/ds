import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { hasGrant } from '$lib/server/auth';

/**
 * Which consent decision is holding up which negotiation.
 *
 * The operator-facing half of the consent flow: `GET /consent/my` already shows a
 * *subject* their pending requests, but nothing showed the provider why a
 * consumer's negotiation has been sitting there. This is a provider-local read
 * over this connector's own table — no protocol involvement, and nothing is asked
 * of the counterparty.
 *
 * Unlike `GET /consent/pending`, this **does** name subjects: an operator of the
 * provider is looking at their own participant's consent records. The
 * counterparty is who must not see them.
 */
export const load: PageServerLoad = async ({ url, locals, fetch, parent }) => {
	await parent(); // provider authority
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const status = url.searchParams.get('status') ?? 'pending';

	const query = status === 'all' ? '' : `?status=${encodeURIComponent(status)}`;

	try {
		const res = await fetch(`${connectorUrl}/consent/asks${query}`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => res.statusText)}`);
		const asks = await res.json();
		return {
			asks: Array.isArray(asks) ? asks : [],
			status,
			// Seeding a request is a write; a read-only provider should not be
			// offered a button the API would refuse.
			maySeed: hasGrant(session, 'connector.provider.write'),
			error: null,
		};
	} catch (e) {
		return {
			asks: [],
			status,
			maySeed: false,
			error: e instanceof Error ? e.message : 'Could not read the consent queue',
		};
	}
};
