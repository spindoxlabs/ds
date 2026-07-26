import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { hasGrant } from '$lib/server/auth';

/**
 * What a producer needs on arrival: what am I publishing, who is asking, and is
 * anything waiting on me.
 *
 * `/consent/asks` is the "waiting on me" signal — a consumer's negotiation parked
 * on a consent decision. Surfacing only the count here; the queue itself is a
 * later phase. It is read with the same `connector.provider.read` the portal
 * already holds.
 */
export const load: PageServerLoad = async ({ locals, fetch, parent }) => {
	await parent(); // the layout guard establishes provider authority
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

	const list = async (path: string): Promise<unknown[] | null> => {
		try {
			const res = await fetch(`${connectorUrl}${path}`, { headers: authHeaders });
			if (!res.ok) return null;
			const body = await res.json();
			return Array.isArray(body) ? body : (body?.datasets ?? null);
		} catch {
			return null;
		}
	};

	const [assets, transfers, asks] = await Promise.all([
		list('/provider/assets'),
		list('/provider/transfers'),
		list('/consent/asks?status=pending'),
	]);

	return {
		counts: {
			assets: assets?.length ?? null,
			transfers: transfers?.length ?? null,
			pendingAsks: asks?.length ?? null,
		},
		may: {
			sync: hasGrant(session, 'connector.provider.write'),
		},
	};
};
