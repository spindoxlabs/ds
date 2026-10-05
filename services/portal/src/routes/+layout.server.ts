import type { LayoutServerLoad } from './$types';
import { derivePersona } from '$lib/server/persona';
import { displaySession } from '$lib/server/session';

export const load: LayoutServerLoad = async (event) => {
	const session = await event.locals.auth();
	const subjectId = session?.userDid ?? '';
	// Every role the user holds, so the nav can show all the sections they
	// qualify for at once rather than picking one.
	const userVcRoles = session?.user ? (session.userVcRoles ?? []) : [];
	const userVcRole = session?.user ? (session.userVcRole ?? null) : null;
	// The nav persona is derived here, not in the browser, so it expands bundle
	// groups and applies group aliases exactly as the route guards do.
	const persona = derivePersona(session);
	// Display data only. The session holds the person's token and credentials,
	// and whatever a layout returns is in every page and every `__data.json`.
	return { session: displaySession(session), subjectId, userVcRoles, userVcRole, persona };
};
