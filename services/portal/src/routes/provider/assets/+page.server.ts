import { fail } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import { listProviderAssets, syncGovernance } from '$lib/server/connector';
import { requireProvider } from '$lib/server/auth';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	try {
		const assets = await listProviderAssets(token);
		return { assets, error: null };
	} catch (e) {
		return { assets: [], error: e instanceof Error ? e.message : 'Failed to load assets' };
	}
};

export const actions: Actions = {
	sync: async (event) => {
		const { session, roles } = await requireProvider(event);
		const token = session?.accessToken ?? '';
		if (!roles.isAdmin && roles.organizations.length === 0) {
			return fail(403, { error: 'You must belong to a dataset owner organization to sync' });
		}
		try {
			const result = await syncGovernance(token);
			return { synced: result.synced };
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Sync failed' });
		}
	},
};
