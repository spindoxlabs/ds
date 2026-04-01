import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';

	try {
		const res = await fetch(`${connectorUrl}/consumer/transfers`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!res.ok) throw new Error(`${res.status}`);
		const transfers = await res.json();
		return { transfers: Array.isArray(transfers) ? transfers : [], error: null };
	} catch (e) {
		return { transfers: [], error: e instanceof Error ? e.message : 'Failed' };
	}
};
