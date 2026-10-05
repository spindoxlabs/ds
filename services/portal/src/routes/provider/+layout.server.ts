import type { LayoutServerLoad } from './$types';
import { requireProvider } from '$lib/server/auth';

export const load: LayoutServerLoad = async (event) => {
	const { roles } = await requireProvider(event);
	return { roles };
};
