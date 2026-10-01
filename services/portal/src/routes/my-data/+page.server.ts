import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { requireDataSubject } from '$lib/server/auth';
import {
	getMyDataShares,
	getSharingOffers,
	setMyDataShare,
	setMyOfferShare,
	type DataShareDecision,
	type OwnedDataset,
	type SharingOffer,
} from '$lib/server/connector';
import { subjectCustody } from '$lib/server/custody';
import { ServiceError } from '$lib/service-error';
import { explainSubjectFailure, type Problem, type SubjectSection } from '$lib/subject-problems';
import { queryMyEvents, type EventPage } from '$lib/server/provenance';

async function loadOwnedDatasets(fetchFn: typeof fetch, subjectId: string): Promise<OwnedDataset[]> {
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
	const url = `${catalogueUrl}/subjects/${encodeURIComponent(subjectId)}/datasets`;
	const res = await fetchFn(url);
	if (!res.ok) throw new ServiceError(res.status, url, await res.text().catch(() => res.statusText));
	const body = await res.json();
	return body?.datasets ?? [];
}

const EMPTY_TIMELINE: EventPage = { events: [], total: 0, limit: 10, offset: 0 };

export const load: PageServerLoad = async ({ locals, fetch, url }) => {
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
			datasets: [] as OwnedDataset[],
			timeline: EMPTY_TIMELINE,
			problems: [] as Problem[],
		};
	}

	// Sharing offers are the primary view — they are what the person was asked.
	// The dataset-derived list is kept as a "what data do I actually have"
	// detail view, not as the consent surface: raw dataset keys are not
	// something anyone consents to.
	//
	// What has actually happened with this person's data (GDPR Art. 15) is read
	// with their own credential — provenance takes the subject from the
	// credential, not from a parameter, so this cannot be pointed at anyone else.
	//
	// Each part fails on its own: a data plane without the per-person dataset
	// list must not hide the sharing choices, nor the other way round.
	const [offers, shares, datasets, timeline] = await Promise.allSettled([
		getSharingOffers(),
		getMyDataShares(token, subjectId, vcJws),
		loadOwnedDatasets(fetch, subjectId),
		queryMyEvents({ limit: 10 }, subjectId, vcJws),
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
		datasets: settled('datasets', datasets, [] as OwnedDataset[]),
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
	share: async ({ request, locals, url }) => {
		const { session, subjectId, vcJws } = await requireDataSubject({ locals, url });
		const token = session.accessToken ?? '';
		const form = await request.formData();
		const datasetId = String(form.get('dataset_id') ?? '');
		const purpose = String(form.get('purpose') ?? '')
			.split(',')
			.map((p) => p.trim())
			.filter(Boolean);
		if (!datasetId) return fail(400, { error: 'dataset_id is required' });
		try {
			await setMyDataShare(token, subjectId, datasetId, true, vcJws, purpose);
		} catch (e) {
			return fail(500, { problem: explainSubjectFailure('change', e) });
		}
		throw redirect(303, '/my-data');
	},
	stop: async ({ request, locals, url }) => {
		const { session, subjectId, vcJws } = await requireDataSubject({ locals, url });
		const token = session.accessToken ?? '';
		const form = await request.formData();
		const datasetId = String(form.get('dataset_id') ?? '');
		if (!datasetId) return fail(400, { error: 'dataset_id is required' });
		try {
			await setMyDataShare(token, subjectId, datasetId, false, vcJws);
		} catch (e) {
			return fail(500, { problem: explainSubjectFailure('change', e) });
		}
		throw redirect(303, '/my-data');
	},
};
