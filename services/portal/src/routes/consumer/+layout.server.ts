import type { LayoutServerLoad } from './$types';
import { requireConsumer } from '$lib/server/auth';

export const load: LayoutServerLoad = async (event) => {
	const { subjectId, userVcRole } = await requireConsumer(event);
	return { subjectId, userVcRole };
};
