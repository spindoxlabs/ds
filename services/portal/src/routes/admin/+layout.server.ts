import type { LayoutServerLoad } from './$types';
import { requireAdmin } from '$lib/server/auth';

export const load: LayoutServerLoad = async (event) => {
	const { session, roles } = await requireAdmin(event);
	return { session, roles };
};
