import type { PageServerLoad } from './$types';
import { listProviderContracts } from '$lib/server/connector';

export const load: PageServerLoad = async ({ params, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const assetId = decodeURIComponent(params.id);

	try {
		const allContracts = await listProviderContracts(token);
		const contracts = allContracts.filter((c) => c.asset_id === assetId);
		return { assetId, contracts, error: null };
	} catch (e) {
		return { assetId, contracts: [], error: e instanceof Error ? e.message : 'Failed' };
	}
};
