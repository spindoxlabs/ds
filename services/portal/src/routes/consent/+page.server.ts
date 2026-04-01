import type { PageServerLoad } from './$types';
import { getMyConsents } from '$lib/server/connector';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	try {
		const consents = await getMyConsents(token);
		return { consents, error: null };
	} catch (e) {
		return { consents: [], error: e instanceof Error ? e.message : 'Failed to load consents' };
	}
};
