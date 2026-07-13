import type { PageServerLoad } from './$types';
import { getMyConsents, subjectFromAccessToken } from '$lib/server/connector';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = subjectFromAccessToken(token);
	try {
		const consents = await getMyConsents(token, subjectId);
		return { consents, subjectId, error: null };
	} catch (e) {
		return { consents: [], subjectId, error: e instanceof Error ? e.message : 'Failed to load consents' };
	}
};
