import type { PageServerLoad } from './$types';
import { summarisePolicy } from '$lib/server/odrl';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ params, locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const assetId = decodeURIComponent(params.id);
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';

	try {
		const res = await fetch(`${catalogueUrl}/catalogue/${encodeURIComponent(assetId)}`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!res.ok) throw new Error(`${res.status}`);
		const dataset = await res.json() as Record<string, unknown>;

		const rawPolicy = dataset['odrl:hasPolicy'];
		const policy = Array.isArray(rawPolicy) ? rawPolicy[0] : rawPolicy;
		const policySummary = summarisePolicy(policy as Record<string, unknown> ?? null);

		return { dataset, policySummary, assetId, error: null };
	} catch (e) {
		return { dataset: null, policySummary: null, assetId, error: e instanceof Error ? e.message : 'Not found' };
	}
};
