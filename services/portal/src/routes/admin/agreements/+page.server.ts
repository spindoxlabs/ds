import type { PageServerLoad } from './$types';
import { requireGrant } from '$lib/server/auth';
import { listAcceptances, listAgreements, type AgreementAcceptance } from '$lib/server/identity-registry';

/**
 * Agreement versions and who accepted what.
 *
 * The capacity an organisation signed under is not cosmetic: it is what the
 * connector's circle check reads to decide whether a requesting party is a
 * processor of the controller (disclosed under a DPA) or an independent
 * controller (a new question for the data subject). So "who accepted which
 * version, in what capacity" is an operator's answer to why a consent question
 * did or did not get asked.
 */
export const load: PageServerLoad = async (event) => {
	const session = await requireGrant(event, 'identity-registry.agreements.read');
	const token = session.accessToken ?? '';

	try {
		const agreements = await listAgreements(token);
		// One request per agreement id; the set is small and operator-facing.
		const ids = [...new Set(agreements.map((a) => a.id))];
		const acceptances = await Promise.all(
			ids.map((id) =>
				listAcceptances(token, id)
					.then((rows) => [id, rows] as const)
					.catch(() => [id, [] as AgreementAcceptance[]] as const),
			),
		);
		return {
			agreements,
			acceptances: Object.fromEntries(acceptances) as Record<string, AgreementAcceptance[]>,
			error: null,
		};
	} catch (e) {
		return {
			agreements: [],
			acceptances: {} as Record<string, AgreementAcceptance[]>,
			error: e instanceof Error ? e.message : 'The identity registry is unavailable',
		};
	}
};
