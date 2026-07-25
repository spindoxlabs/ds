import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { redirect } from '@sveltejs/kit';
import { hasVcRole, parseTokenRoles } from '$lib/server/auth';

export const load: PageServerLoad = async ({ locals, fetch, url }) => {
	const session = await locals.auth();
	if (!session?.user || session.error === 'RefreshTokenError') {
		throw redirect(303, `/auth/signin?callbackUrl=${encodeURIComponent(url.pathname)}`);
	}

	const roles = parseTokenRoles(session.accessToken);
	// Redirect only when the catalogue is genuinely not this user's page, and only
	// when exactly one other path applies. Ranking roles by priority bounced a
	// user who holds several away from a section they are entitled to.
	if (!roles.isAdmin && !hasVcRole(session, 'ConsumerUser')) {
		const isSubject = hasVcRole(session, 'DataSubject');
		if (roles.isDatasetAdmin && !isSubject) {
			throw redirect(303, '/provider/assets');
		}
		if (isSubject && !roles.isDatasetAdmin) {
			throw redirect(303, '/my-data');
		}
		// Both (or neither) apply: leave them here, where the nav shows every
		// section they qualify for.
	}

	// Use federated catalog when configured; fall back to dataset-api catalogue.
	const federatedUrl = env.FEDERATED_CATALOG_URL;
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
	const token = session?.accessToken ?? '';
	const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

	if (federatedUrl) {
		try {
			const res = await fetch(`${federatedUrl}/catalog?limit=50`, { headers });
			if (!res.ok) throw new Error(`${res.status}`);
			const data = await res.json();
			const datasets: unknown[] = data?.['dcat:dataset'] ?? [];
			if (datasets.length > 0) {
				return { datasets, federated: true, error: null };
			}
		} catch (e) {
			console.error('[ds-portal] Federated catalog unavailable, falling back to dataset-api:', e instanceof Error ? e.message : e);
		}
	}

	try {
		const res = await fetch(`${catalogueUrl}/catalogue`, { headers });
		if (!res.ok) throw new Error(`${res.status}`);
		const data = await res.json();
		const datasets: unknown[] = Array.isArray(data) ? data : (data?.datasets ?? data?.['dcat:dataset'] ?? []);
		return { datasets, federated: false, error: null };
	} catch (e) {
		console.error('[ds-portal] Catalogue load failed:', e instanceof Error ? e.message : e);
		return { datasets: [], federated: false, error: 'Catalogue is temporarily unavailable.' };
	}
};
