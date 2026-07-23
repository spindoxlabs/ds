import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { requireDataSubject } from '$lib/server/auth';
import {
	getMyDataShares,
	getSharingOffers,
	setMyDataShare,
	setMyOfferShare,
	type OwnedDataset,
	type SharingOffer,
} from '$lib/server/connector';

async function loadOwnedDatasets(fetchFn: typeof fetch, subjectId: string): Promise<OwnedDataset[]> {
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
	const res = await fetchFn(`${catalogueUrl}/subjects/${encodeURIComponent(subjectId)}/datasets`);
	if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => res.statusText)}`);
	const body = await res.json();
	return body?.datasets ?? [];
}

export const load: PageServerLoad = async ({ locals, fetch, url }) => {
	const { session, subjectId } = await requireDataSubject({ locals, url });
	const token = session.accessToken ?? '';
	const vcJws = session.userVcJws;

	// Sharing offers are the primary view — they are what the person was asked.
	// The dataset-derived list is kept as a "what data do I actually have"
	// detail view, not as the consent surface: raw dataset keys are not
	// something anyone consents to.
	let offers: SharingOffer[] = [];
	let offersError: string | null = null;
	try {
		offers = await getSharingOffers();
	} catch (e) {
		offersError = e instanceof Error ? e.message : 'Failed to load sharing offers';
	}

	try {
		const [datasets, shares] = await Promise.all([
			loadOwnedDatasets(fetch, subjectId),
			getMyDataShares(token, subjectId, vcJws),
		]);
		return { subjectId, offers, offersError, datasets, shares, error: null };
	} catch (e) {
		return {
			subjectId,
			offers,
			offersError,
			datasets: [],
			shares: [],
			error: e instanceof Error ? e.message : 'Failed to load owned datasets',
		};
	}
};

export const actions: Actions = {
	shareOffer: async ({ request, locals, url }) => {
		const { session, subjectId } = await requireDataSubject({ locals, url });
		const form = await request.formData();
		const offerId = String(form.get('offer_id') ?? '');
		const enabled = String(form.get('enabled') ?? '') === 'true';
		if (!offerId) return fail(400, { error: 'offer_id is required' });
		try {
			await setMyOfferShare(session.accessToken ?? '', subjectId, offerId, enabled, session.userVcJws);
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Failed to update sharing' });
		}
		throw redirect(303, '/my-data');
	},
	share: async ({ request, locals, url }) => {
		const { session, subjectId } = await requireDataSubject({ locals, url });
		const token = session.accessToken ?? '';
		const form = await request.formData();
		const datasetId = String(form.get('dataset_id') ?? '');
		const purpose = String(form.get('purpose') ?? '')
			.split(',')
			.map((p) => p.trim())
			.filter(Boolean);
		if (!datasetId) return fail(400, { error: 'dataset_id is required' });
		try {
			await setMyDataShare(token, subjectId, datasetId, true, session.userVcJws, purpose);
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Failed to enable sharing' });
		}
		throw redirect(303, '/my-data');
	},
	stop: async ({ request, locals, url }) => {
		const { session, subjectId } = await requireDataSubject({ locals, url });
		const token = session.accessToken ?? '';
		const form = await request.formData();
		const datasetId = String(form.get('dataset_id') ?? '');
		if (!datasetId) return fail(400, { error: 'dataset_id is required' });
		try {
			await setMyDataShare(token, subjectId, datasetId, false, session.userVcJws);
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Failed to disable sharing' });
		}
		throw redirect(303, '/my-data');
	},
};
