import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { requireDataSubject } from '$lib/server/auth';
import {
	getMyDataShares,
	getSharingOffers,
	setMyOfferShare,
	type DataShareDecision,
	type SharingOffer,
} from '$lib/server/connector';
import { subjectCustody } from '$lib/server/custody';
import { explainSubjectFailure, type Problem, type SubjectSection } from '$lib/subject-problems';
import { queryMyEvents, type EventPage } from '$lib/server/provenance';

const EMPTY_TIMELINE: EventPage = { events: [], total: 0, limit: 10, offset: 0 };

export const load: PageServerLoad = async ({ locals, url }) => {
	const { session, subjectId, vcJws } = await requireDataSubject({ locals, url });
	const token = session.accessToken ?? '';
	const custody = subjectCustody(subjectId);

	// Every call below would be refused: the connector accepts this person's
	// credential only at the participant that holds it.
	if (!custody.isHome) {
		return {
			subjectId,
			custody,
			offers: [] as SharingOffer[],
			shares: [] as DataShareDecision[],
			sharesKnown: false,
			timeline: EMPTY_TIMELINE,
			problems: [] as Problem[],
		};
	}

	// Sharing offers are the primary view — they are what the person was asked.
	//
	// What has actually happened with this person's data (GDPR Art. 15) is read
	// with their own credential — provenance takes the subject from the
	// credential, not from a parameter, so this cannot be pointed at anyone else.
	//
	// Each part fails on its own: an unreachable provenance log must not hide
	// the sharing choices, nor the other way round.
	const [offers, shares, timeline] = await Promise.allSettled([
		getSharingOffers(),
		getMyDataShares(token, subjectId, vcJws),
		queryMyEvents({ limit: 10 }, token, subjectId, vcJws),
	]);

	const problems: Problem[] = [];
	function settled<T>(section: SubjectSection, result: PromiseSettledResult<T>, fallback: T): T {
		if (result.status === 'fulfilled') return result.value;
		problems.push(explainSubjectFailure(section, result.reason));
		return fallback;
	}

	return {
		subjectId,
		custody,
		offers: settled('sharing', offers, [] as SharingOffer[]),
		shares: settled('sharing', shares, [] as DataShareDecision[]),
		// Without the decisions, "not shared" on every offer would be a claim
		// this page cannot make — the offers render read-only instead.
		sharesKnown: shares.status === 'fulfilled',
		timeline: settled('activity', timeline, EMPTY_TIMELINE),
		problems,
	};
};

export const actions: Actions = {
	shareOffer: async ({ request, locals, url }) => {
		const { session, subjectId, vcJws } = await requireDataSubject({ locals, url });
		const form = await request.formData();
		const offerId = String(form.get('offer_id') ?? '');
		const enabled = String(form.get('enabled') ?? '') === 'true';
		if (!offerId) return fail(400, { error: 'offer_id is required' });
		try {
			await setMyOfferShare(session.accessToken ?? '', subjectId, offerId, enabled, vcJws);
		} catch (e) {
			return fail(500, { problem: explainSubjectFailure('change', e) });
		}
		throw redirect(303, '/my-data');
	},
};
