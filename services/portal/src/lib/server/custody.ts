import { env } from '$env/dynamic/private';
import { custodyOf, type Custody } from '$lib/subject-problems';

/**
 * Whether this portal's participant holds the person's credentials.
 *
 * The connector accepts a member credential only where `linkedParticipant` is
 * its own participant, so on any other portal the subject pages would get a
 * refusal for every call. Knowing that up front lets them say where the
 * person's data is managed instead of making calls that cannot succeed.
 */
export function subjectCustody(subjectDid: string): Custody {
	return custodyOf(subjectDid, env.PARTICIPANT_DID);
}
