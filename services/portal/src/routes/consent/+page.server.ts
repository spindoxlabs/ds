import type { PageServerLoad } from './$types';
import { getMyConsents, type ConsentRequest } from '$lib/server/connector';
import { vcJwsForRole } from '$lib/server/auth';
import { subjectCustody } from '$lib/server/custody';
import { explainSubjectFailure, type Problem } from '$lib/subject-problems';

export const load: PageServerLoad = async ({ locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session?.userDid ?? '';
	const custody = subjectCustody(subjectId);
	// Refused by the connector anyway: it accepts this person's credential only
	// at the participant that holds it.
	if (!custody.isHome) {
		return { consents: [] as ConsentRequest[], subjectId, custody, problems: [] as Problem[] };
	}
	try {
		const consents = await getMyConsents(token, subjectId, vcJwsForRole(session, 'DataSubject'));
		return { consents, subjectId, custody, problems: [] as Problem[] };
	} catch (e) {
		return {
			consents: [] as ConsentRequest[],
			subjectId,
			custody,
			problems: [explainSubjectFailure('consents', e)],
		};
	}
};
