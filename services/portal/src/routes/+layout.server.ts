import type { LayoutServerLoad } from './$types';
import { subjectFromAccessToken, userVcRoleForSubject } from '$lib/server/connector';

export const load: LayoutServerLoad = async (event) => {
	const session = await event.locals.auth();
	const subjectId = subjectFromAccessToken(session?.accessToken);
	const userVcRole = session?.user ? userVcRoleForSubject(subjectId) : null;
	return { session, subjectId, userVcRole };
};
