import type { PageServerLoad } from './$types';
import { queryEvents, type EventQuery } from '$lib/server/provenance';

const PAGE_SIZE = 50;

/**
 * Every event this participant recorded.
 *
 * Each participant runs its own provenance store, so this is already scoped to
 * one participant by deployment — there is no cross-participant read to guard
 * against. Filters come straight from the query string so a view is a URL an
 * operator can share or bookmark.
 */
export const load: PageServerLoad = async ({ url, locals, parent }) => {
	await parent(); // operator authority
	const session = await locals.auth();
	const token = session?.accessToken ?? '';

	const query: EventQuery = {
		event_type: url.searchParams.getAll('event_type').filter(Boolean),
		dataset_id: url.searchParams.get('dataset_id') ?? undefined,
		subject_id: url.searchParams.get('subject_id') ?? undefined,
		consumer_did: url.searchParams.get('consumer_did') ?? undefined,
		occurred_after: url.searchParams.get('occurred_after') || undefined,
		occurred_before: url.searchParams.get('occurred_before') || undefined,
		limit: PAGE_SIZE,
		offset: Number(url.searchParams.get('offset') ?? 0) || 0,
	};

	try {
		const page = await queryEvents(query, token);
		return { page, query, error: null };
	} catch (e) {
		return {
			page: { events: [], total: 0, limit: PAGE_SIZE, offset: 0 },
			query,
			error: e instanceof Error ? e.message : 'Provenance is unavailable',
		};
	}
};
