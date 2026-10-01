import { fail, redirect } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import { getMyConsent, approveConsent, rejectConsent, revokeConsent } from '$lib/server/connector';
import { datasetPolicySummary } from '$lib/server/catalog';
import { vcJwsForRole } from '$lib/server/auth';
import { subjectCustody } from '$lib/server/custody';
import { explainSubjectFailure, type Problem } from '$lib/subject-problems';

export const load: PageServerLoad = async ({ params, locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session?.userDid ?? '';
	const vcJws = vcJwsForRole(session, 'DataSubject');
	const custody = subjectCustody(subjectId);
	if (!custody.isHome) {
		return { consent: null, policySummary: null, subjectId, custody, problems: [] as Problem[] };
	}
	try {
		const consent = await getMyConsent(params.id, token, subjectId, vcJws);
		// The governing policy is the dataset's own ODRL, summarised from the same
		// source the catalog page reads — not `null`, which rendered nothing.
		const policySummary = await datasetPolicySummary(consent.dataset_id, token, fetch);
		return { consent, policySummary, subjectId, custody, problems: [] as Problem[] };
	} catch (e) {
		return {
			consent: null,
			policySummary: null,
			subjectId,
			custody,
			problems: [explainSubjectFailure('consent', e)],
		};
	}
};

export const actions: Actions = {
	approve: async ({ params, locals }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		const subjectId = session?.userDid ?? '';
		try {
			await approveConsent(params.id, token, subjectId, vcJwsForRole(session, 'DataSubject'));
		} catch (e) {
			return fail(500, { problem: explainSubjectFailure('change', e) });
		}
		throw redirect(303, '/consent');
	},
	reject: async ({ params, locals }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		const subjectId = session?.userDid ?? '';
		try {
			await rejectConsent(params.id, token, subjectId, vcJwsForRole(session, 'DataSubject'));
		} catch (e) {
			return fail(500, { problem: explainSubjectFailure('change', e) });
		}
		throw redirect(303, '/consent');
	},
	revoke: async ({ params, locals }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		const subjectId = session?.userDid ?? '';
		try {
			await revokeConsent(params.id, token, subjectId, vcJwsForRole(session, 'DataSubject'));
		} catch (e) {
			return fail(500, { problem: explainSubjectFailure('change', e) });
		}
		throw redirect(303, '/consent');
	},
};
