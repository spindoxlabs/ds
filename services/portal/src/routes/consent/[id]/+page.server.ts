import { fail, redirect } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import { getMyConsent, approveConsent, rejectConsent, revokeConsent } from '$lib/server/connector';
import { summarisePolicy } from '$lib/server/odrl';

export const load: PageServerLoad = async ({ params, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	try {
		const consent = await getMyConsent(params.id, token);
		// Policy is stored in consent.purpose as a list; no full ODRL here — use message field
		const policySummary = summarisePolicy(null);
		return { consent, policySummary, error: null };
	} catch (e) {
		return { consent: null, policySummary: null, error: e instanceof Error ? e.message : 'Not found' };
	}
};

export const actions: Actions = {
	approve: async ({ params, locals }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		try {
			await approveConsent(params.id, token);
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Failed' });
		}
		throw redirect(303, '/consent');
	},
	reject: async ({ params, locals }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		try {
			await rejectConsent(params.id, token);
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Failed' });
		}
		throw redirect(303, '/consent');
	},
	revoke: async ({ params, locals }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		try {
			await revokeConsent(params.id, token);
		} catch (e) {
			return fail(500, { error: e instanceof Error ? e.message : 'Failed' });
		}
		throw redirect(303, '/consent');
	},
};
