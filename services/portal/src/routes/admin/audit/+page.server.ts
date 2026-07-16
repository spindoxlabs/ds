import type { PageServerLoad } from './$types';
import { queryEvents } from '$lib/server/provenance';

export const load: PageServerLoad = async ({ url, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';

	const params: Record<string, string> = {};
	const eventType = url.searchParams.get('event_type');
	if (eventType) params['event_type'] = eventType;
	const after = url.searchParams.get('occurred_after');
	if (after) params['occurred_after'] = after;

	try {
		const events = await queryEvents(params, token);
		return { events, error: null };
	} catch (e) {
		return { events: [], error: e instanceof Error ? e.message : 'Failed' };
	}
};
