import type { PageServerLoad } from './$types';
import { listProviderContracts } from '$lib/server/connector';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	try {
		const contracts = await listProviderContracts(token);
		return { contracts, error: null };
	} catch (e) {
		return { contracts: [], error: e instanceof Error ? e.message : 'Failed' };
	}
};
