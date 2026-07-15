import type { PageServerLoad } from './$types';
import { getMyConsents } from '$lib/server/connector';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session?.userDid ?? '';
	try {
		const consents = await getMyConsents(token, subjectId, session?.userVcJws);
		return { consents, subjectId, error: null };
	} catch (e) {
		return { consents: [], subjectId, error: e instanceof Error ? e.message : 'Failed to load consents' };
	}
};
