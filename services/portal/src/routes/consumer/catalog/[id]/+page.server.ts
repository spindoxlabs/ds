import type { PageServerLoad } from './$types';
import { summarisePolicy } from '$lib/server/odrl';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ params, locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const assetId = decodeURIComponent(params.id);
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';

	try {
		const listRes = await fetch(`${catalogueUrl}/catalogue`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!listRes.ok) throw new Error(`${listRes.status}`);
		const raw = await listRes.json();
		const datasets: Array<Record<string, unknown>> = Array.isArray(raw)
			? raw
			: (raw?.datasets ?? raw?.['dcat:dataset'] ?? []);
		let dataset = datasets.find((item) => {
			const ids = [item['dct:identifier'], item['@id'], item['id'], item['asset_id']];
			return ids.map(String).includes(assetId);
		});

		if (!dataset) {
			const res = await fetch(`${catalogueUrl}/catalogue/${encodeURIComponent(assetId)}`, {
				headers: token ? { Authorization: `Bearer ${token}` } : {},
			});
			if (!res.ok) throw new Error(`${res.status}`);
			dataset = await res.json() as Record<string, unknown>;
		}

		const distribution = Array.isArray(dataset['dcat:distribution'])
			? (dataset['dcat:distribution'] as Array<Record<string, unknown>>)[0]
			: null;
		const rawPolicy = dataset['odrl:hasPolicy'] ?? distribution?.['odrl:hasPolicy'];
		const policy = Array.isArray(rawPolicy) ? rawPolicy[0] : rawPolicy;
		const policySummary = summarisePolicy(policy as Record<string, unknown> ?? null);

		return { dataset, policySummary, assetId, error: null };
	} catch (e) {
		return { dataset: null, policySummary: null, assetId, error: e instanceof Error ? e.message : 'Not found' };
	}
};
