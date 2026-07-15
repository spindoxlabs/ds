import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async (event) => {
	const session = await event.locals.auth();
	const subjectId = session?.userDid ?? '';
	const userVcRole = session?.user ? (session.userVcRole ?? null) : null;
	return { session, subjectId, userVcRole };
};
