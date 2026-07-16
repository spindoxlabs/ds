import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { redirect } from '@sveltejs/kit';
import { parseTokenRoles } from '$lib/server/auth';

export const load: PageServerLoad = async ({ locals, fetch, url }) => {
	const session = await locals.auth();
	if (!session?.user) {
		throw redirect(303, `/auth/signin?callbackUrl=${encodeURIComponent(url.pathname)}`);
	}

	const roles = parseTokenRoles(session.accessToken);
	const userVcRole = session.userVcRole ?? null;
	if (!roles.isAdmin && userVcRole !== 'ConsumerUser') {
		if (roles.isDatasetAdmin) {
			throw redirect(303, '/provider/assets');
		}
		if (userVcRole === 'DataSubject') {
			throw redirect(303, '/my-data');
		}
	}

	// Use federated catalog when configured; fall back to dataset-api catalogue.
	const federatedUrl = env.FEDERATED_CATALOG_URL;
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';

	try {
		if (federatedUrl) {
			const res = await fetch(`${federatedUrl}/catalog?limit=50`);
			if (!res.ok) throw new Error(`federated-catalog: ${res.status}`);
			const data = await res.json();
			const datasets: unknown[] = data?.['dcat:dataset'] ?? [];
			if (datasets.length > 0) {
				return { datasets, federated: true, error: null };
			}
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
