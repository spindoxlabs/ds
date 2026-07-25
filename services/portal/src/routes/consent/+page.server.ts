import type { PageServerLoad } from './$types';
import { getMyConsents } from '$lib/server/connector';
import { vcJwsForRole } from '$lib/server/auth';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session?.userDid ?? '';
	try {
		const consents = await getMyConsents(token, subjectId, vcJwsForRole(session, 'DataSubject'));
		return { consents, subjectId, error: null };
	} catch (e) {
		return { consents: [], subjectId, error: e instanceof Error ? e.message : 'Failed to load consents' };
	}
};
