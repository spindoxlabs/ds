/**
 * What the data-subject pages say when something did not load.
 *
 * A person reading their own data should get a sentence they can act on, not a
 * status code and a backend URL. The raw text is still kept — as `technical` —
 * and the pages put it in a collapsed block at the bottom, where whoever runs
 * the deployment can read it.
 */
import { ServiceError } from './service-error';

export type ProblemTone = 'info' | 'warning' | 'error';

export interface Problem {
	/** Which part of the page this is about, for the technical block's heading. */
	section: SubjectSection;
	title: string;
	message: string;
	tone: ProblemTone;
	/** The unedited error, for the technical block. */
	technical: string;
}

export type SubjectSection = 'sharing' | 'activity' | 'consents' | 'consent' | 'change';

const SECTIONS: Record<SubjectSection, { verb: string; noun: string; label: string }> = {
	sharing: { verb: 'load', noun: 'your sharing choices', label: 'Sharing' },
	activity: { verb: 'load', noun: 'your activity history', label: 'What happened with your data' },
	consents: { verb: 'load', noun: 'your consent requests', label: 'Consent requests' },
	consent: { verb: 'load', noun: 'this consent request', label: 'Consent request' },
	change: { verb: 'save', noun: 'your change', label: 'Your change' },
};

export function sectionLabel(section: SubjectSection): string {
	return SECTIONS[section].label;
}

/** The connector's answer when the credential names another participant. */
const NOT_LINKED = 'User VC is not linked to this participant';

export function explainSubjectFailure(section: SubjectSection, error: unknown): Problem {
	const { verb, noun } = SECTIONS[section];
	const technical = error instanceof Error ? error.message : String(error);
	const problem = (tone: ProblemTone, title: string, message: string): Problem => ({
		section,
		tone,
		title,
		message,
		technical,
	});

	if (!(error instanceof ServiceError)) {
		return problem(
			'error',
			'The service did not respond',
			`We could not ${verb} ${noun}. Try again in a few minutes.`,
		);
	}
	if (error.detail === NOT_LINKED) {
		return problem(
			'warning',
			'Your data is managed by another organisation',
			`This portal belongs to an organisation that does not hold your membership, so it ` +
				`cannot show ${noun}. Use the portal of the organisation you joined.`,
		);
	}
	switch (error.status) {
		case 401:
			return problem(
				'warning',
				'Please sign in again',
				`Your sign-in could not be confirmed, so we could not ${verb} ${noun}. ` +
					'Sign out and sign in again.',
			);
		case 403:
			return problem('warning', 'Not available to you here', `You cannot see ${noun} on this portal.`);
		case 404:
			if (section === 'consent') {
				return problem('warning', 'Request not found', 'This consent request does not exist, or it is not yours.');
			}
			return problem('warning', 'Not available here', `This portal cannot show ${noun}.`);
		default:
			return problem(
				'error',
				error.status >= 500 ? 'Temporarily unavailable' : 'Something went wrong',
				`We could not ${verb} ${noun}. Try again in a few minutes.`,
			);
	}
}

// ── Whose data this portal holds ────────────────────────────────────────────

/** The organisation a person's DID is filed under — `did:web:<custodian>:users:<id>`. */
export function custodianOf(did: string): string | null {
	const marker = ':users:';
	const at = did.lastIndexOf(marker);
	return at === -1 || !did.startsWith('did:web:') ? null : did.slice(0, at);
}

export interface Custody {
	/** This portal's participant. */
	here: string | null;
	/** The participant holding the person's credentials. */
	home: string | null;
	/**
	 * False only when both are known and differ. Not knowing either keeps the
	 * pages calling the connector, which still refuses and is still explained.
	 */
	isHome: boolean;
}

export function custodyOf(subjectDid: string, participantDid: string | null | undefined): Custody {
	const here = participantDid || null;
	const home = subjectDid ? custodianOf(subjectDid) : null;
	return { here, home, isHome: !here || !home || here === home };
}

/** `did:web:rec.example.org` → `rec` — a name to show, not to compare. */
export function participantLabel(did: string | null): string {
	if (!did?.startsWith('did:web:')) return did ?? 'unknown';
	const host = decodeURIComponent(did.slice('did:web:'.length).split(':')[0]).split(':')[0];
	return host.split('.')[0] || host;
}
