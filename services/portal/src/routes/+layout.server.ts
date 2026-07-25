import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async (event) => {
	const session = await event.locals.auth();
	const subjectId = session?.userDid ?? '';
	// Every role the user holds, so the nav can show all the sections they
	// qualify for at once rather than picking one.
	const userVcRoles = session?.user ? (session.userVcRoles ?? []) : [];
	const userVcRole = session?.user ? (session.userVcRole ?? null) : null;
	return { session, subjectId, userVcRoles, userVcRole };
};
