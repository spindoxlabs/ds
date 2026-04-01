import type { LayoutServerLoad } from './$types';
import { requireProvider } from '$lib/server/auth';

export const load: LayoutServerLoad = async (event) => {
	const { session, roles } = await requireProvider(event);
	return { session, roles };
};
