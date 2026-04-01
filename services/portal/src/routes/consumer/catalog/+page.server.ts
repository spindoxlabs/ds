import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const federatedUrl = env.FEDERATED_CATALOG_URL;
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';

	// Optional provider filter from URL param
	const providerFilter = url.searchParams.get('provider') ?? undefined;

	try {
		if (federatedUrl) {
			const body: Record<string, unknown> = {};
			if (providerFilter) body.provider = providerFilter;
			const res = await fetch(`${federatedUrl}/catalog/search`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) throw new Error(`federated-catalog: ${res.status}`);
			const raw = await res.json();
			const datasets: unknown[] = raw?.['dcat:dataset'] ?? [];
			return { datasets, federated: true, error: null };
		}
		const res = await fetch(`${catalogueUrl}/catalogue`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!res.ok) throw new Error(`${res.status}`);
		const raw = await res.json();
		const datasets: unknown[] = Array.isArray(raw) ? raw : (raw?.datasets ?? raw?.['dcat:dataset'] ?? []);
		return { datasets, federated: false, error: null };
	} catch (e) {
		return { datasets: [], federated: false, error: e instanceof Error ? e.message : 'Failed' };
	}
};
