import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ fetch }) => {
	// Use federated catalog when configured; fall back to dataset-api catalogue.
	const federatedUrl = env.FEDERATED_CATALOG_URL;
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';

	try {
		if (federatedUrl) {
			const res = await fetch(`${federatedUrl}/catalog?limit=50`);
			if (!res.ok) throw new Error(`federated-catalog: ${res.status}`);
			const data = await res.json();
			const datasets: unknown[] = data?.['dcat:dataset'] ?? [];
			return { datasets, federated: true, error: null };
		}
		const res = await fetch(`${catalogueUrl}/catalogue`);
		if (!res.ok) throw new Error(`${res.status}`);
		const data = await res.json();
		const datasets: unknown[] = Array.isArray(data) ? data : (data?.datasets ?? data?.['dcat:dataset'] ?? []);
		return { datasets, federated: false, error: null };
	} catch (e) {
		return { datasets: [], federated: false, error: e instanceof Error ? e.message : 'Failed to load catalogue' };
	}
};
