import type { PageServerLoad } from './$types';
import { queryEvents, type EventQuery } from '$lib/server/provenance';

const PAGE_SIZE = 25;

/**
 * This participant's provenance, for the provider console.
 *
 * The store belongs to this participant, so there is nothing to scope by here —
 * the operator view and this one read the same events. What differs is the
 * framing and the page size, not the authority.
 */
export const load: PageServerLoad = async ({ url, locals, parent }) => {
	await parent();
	const session = await locals.auth();
	const token = session?.accessToken ?? '';

	const query: EventQuery = {
		event_type: url.searchParams.getAll('event_type').filter(Boolean),
		dataset_id: url.searchParams.get('dataset_id') ?? undefined,
		limit: PAGE_SIZE,
		offset: Number(url.searchParams.get('offset') ?? 0) || 0,
	};

	try {
		return { page: await queryEvents(query, token), error: null };
	} catch (e) {
		return {
			page: { events: [], total: 0, limit: PAGE_SIZE, offset: 0 },
			error: e instanceof Error ? e.message : 'Provenance is unavailable',
		};
	}
};
