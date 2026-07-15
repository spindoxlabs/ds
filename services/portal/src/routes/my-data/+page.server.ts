import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { requireDataSubject } from '$lib/server/auth';
import {
	getMyDataShares,
	setMyDataShare,
	type OwnedDataset,
} from '$lib/server/connector';

async function loadOwnedDatasets(fetchFn: typeof fetch, subjectId: string): Promise<OwnedDataset[]> {
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://dataset-api:30002';
	const res = await fetchFn(`${catalogueUrl}/subjects/${encodeURIComponent(subjectId)}/datasets`);
	if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => res.statusText)}`);
	const body = await res.json();
	return body?.datasets ?? [];
}

export const load: PageServerLoad = async ({ locals, fetch, url }) => {
	const { session, subjectId } = await requireDataSubject({ locals, url });
	const token = session.accessToken ?? '';
	const vcJws = session.userVcJws;

	try {
		const [datasets, shares] = await Promise.all([
			loadOwnedDatasets(fetch, subjectId),
			getMyDataShares(token, subjectId, vcJws),
		]);
		return { subjectId, datasets, shares, error: null };
	} catch (e) {
		return {
			subjectId,
			datasets: [],
			shares: [],
			error: e instanceof Error ? e.message : 'Failed to load owned datasets',
		};
	}
};

export const actions: Actions = {
	share: async ({ request, locals, url }) => {
		const { session, subjectId } = await requireDataSubject({ locals, url });
		const token = session.accessToken ?? '';
		const form = await request.formData();
		const datasetId = String(form.get('dataset_id') ?? '');
		if (!datasetId) return fail(400, { error: 'dataset_id is required' });
		try {
			await setMyDataShare(token, subjectId, datasetId, true, session.userVcJws);
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
