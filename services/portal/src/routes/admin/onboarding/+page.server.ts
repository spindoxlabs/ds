import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { hasGrant, requireGrant } from '$lib/server/auth';
import {
	createInvite,
	decideApplication,
	generateProvisioningBundle,
	issueOrganizationCredential,
	listAgreements,
	listApplications,
	listInvites,
	listOwners,
	listParticipantDids,
	promoteOwner,
	recordAgreementAcceptance,
	updateOwner,
} from '$lib/server/identity-registry';

/**
 * The organisation review queue.
 *
 * Every action calls the same identity-registry endpoint as `ir-cli`. The CLI
 * stays the reference implementation — this console must not become a second way
 * to change trust state, because two paths to the same transition is two chances
 * to disagree about the gates.
 *
 * The gates themselves are enforced by the registry, not here (issue needs a
 * verified owner holding a current agreement; promote needs a valid, unrevoked
 * credential). The page *shows* gate state so the trust model is legible rather
 * than concealed behind a disabled button.
 */
export const load: PageServerLoad = async (event) => {
	const session = await requireGrant(event, 'identity-registry.organizations.read');
	const token = session.accessToken ?? '';
	const status = event.url.searchParams.get('status') ?? 'pending';

	try {
		const [applications, owners, agreements, invites, enrolledDids] = await Promise.all([
			listApplications(token, status),
			listOwners(token).catch(() => []),
			listAgreements(token).catch(() => []),
			listInvites(token).catch(() => []),
			listParticipantDids(token),
		]);
		return {
			applications,
			owners,
			agreements,
			invites,
			enrolledDids,
			status,
			may: {
				write: hasGrant(session, 'identity-registry.organizations.write'),
				promote: hasGrant(session, 'identity-registry.organizations.promote'),
			},
			error: null,
		};
	} catch (e) {
		return {
			applications: [],
			owners: [],
			agreements: [],
			invites: [],
			enrolledDids: [],
			status,
			may: { write: false, promote: false },
			error: e instanceof Error ? e.message : 'The identity registry is unavailable',
		};
	}
};

/** The operator's own identity, recorded as who verified an application. */
function actor(session: { user?: { email?: string | null; name?: string | null } | null }): string {
	return session.user?.email ?? session.user?.name ?? 'operator';
}

export const actions: Actions = {
	/**
	 * Issue an invitation code.
	 *
	 * The code comes back once and is returned to the page so the operator can copy
	 * it — the registry stores only a hash, so there is no second chance to read it.
	 */
	invite: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.write');
		const form = await event.request.formData();
		const ttl = Number(form.get('ttl_days') ?? 30);
		try {
			const issued = await createInvite(session.accessToken ?? '', {
				label: String(form.get('label') ?? '') || undefined,
				ttl_days: Number.isFinite(ttl) && ttl > 0 ? ttl : undefined,
			});
			return { issuedCode: issued.code, issuedLabel: issued.label ?? null };
		} catch (e) {
			return fail(502, { error: e instanceof Error ? e.message : 'Could not issue an invite' });
		}
	},

	decide: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.write');
		const form = await event.request.formData();
		const id = String(form.get('id') ?? '');
		const status = String(form.get('status') ?? '') as 'verified' | 'rejected';
		if (!id || !['verified', 'rejected'].includes(status)) {
			return fail(400, { error: 'A decision needs an application and a status' });
		}
		try {
			await decideApplication(session.accessToken ?? '', id, {
				status,
				verified_by: actor(session),
				evidence_ref: String(form.get('evidence_ref') ?? '') || undefined,
				notes: String(form.get('notes') ?? '') || undefined,
			});
		} catch (e) {
			return fail(502, { error: e instanceof Error ? e.message : 'Decision failed' });
		}
		throw redirect(303, `/admin/onboarding?status=${event.url.searchParams.get('status') ?? 'pending'}`);
	},

	acceptAgreement: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.write');
		const form = await event.request.formData();
		const alias = String(form.get('alias') ?? '');
		const [agreementId, version] = String(form.get('agreement') ?? '').split('@');
		if (!alias || !agreementId || !version) {
			return fail(400, { error: 'Choose an agreement version to record' });
		}
		try {
			await recordAgreementAcceptance(session.accessToken ?? '', alias, {
				agreement_id: agreementId,
				version,
				accepted_by: actor(session),
			});
		} catch (e) {
			return fail(502, { error: e instanceof Error ? e.message : 'Could not record acceptance' });
		}
		throw redirect(303, '/admin/onboarding?status=verified');
	},

	/** Assign the `did:web` the credential gate requires. */
	setDid: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.write');
		const form = await event.request.formData();
		const alias = String(form.get('alias') ?? '');
		const did = String(form.get('did') ?? '').trim();
		if (!alias || !did) return fail(400, { error: 'Both the organisation and a DID are required' });
		try {
			await updateOwner(session.accessToken ?? '', alias, { did });
		} catch (e) {
			return fail(502, { error: e instanceof Error ? e.message : 'Could not set the DID' });
		}
		throw redirect(303, '/admin/onboarding?status=verified');
	},

	issueCredential: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.write');
		const form = await event.request.formData();
		const alias = String(form.get('alias') ?? '');
		if (!alias) return fail(400, { error: 'Missing organisation' });
		try {
			await issueOrganizationCredential(session.accessToken ?? '', alias);
		} catch (e) {
			// IR refuses when the gate is unmet; its message names which gate.
			return fail(502, { error: e instanceof Error ? e.message : 'Could not issue the credential' });
		}
		throw redirect(303, '/admin/onboarding?status=verified');
	},

	/**
	 * Hand a promoted organisation its connection bundle.
	 *
	 * Carries a **single-use enrolment code**, so the page warns before and
	 * after. Returned to the page rather than downloaded server-side: the
	 * operator saves it once, and it never touches disk here.
	 *
	 * It no longer rotates anything — the registry mints no STS secret for a
	 * participant (`DID-10`/`D-51`). Reissuing is therefore safe for an existing
	 * deployment, and is *not* revocation: the earlier code stays valid until
	 * redeemed or expired.
	 *
	 * One registry call renders all three artefacts. Asking three times would
	 * issue three codes where the recipient needs one.
	 */
	bundle: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.promote');
		const form = await event.request.formData();
		const alias = String(form.get('alias') ?? '');
		if (!alias) return fail(400, { error: 'Missing organisation' });
		try {
			const rendered = await generateProvisioningBundle(session.accessToken ?? '', alias);
			return {
				bundle: JSON.stringify(rendered.bundle, null, 2),
				bundleEnv: rendered.env,
				bundleProperties: rendered.properties,
				bundleAlias: alias,
			};
		} catch (e) {
			return fail(502, { error: e instanceof Error ? e.message : 'Could not generate a bundle' });
		}
	},

	promote: async (event) => {
		const session = await requireGrant(event, 'identity-registry.organizations.promote');
		const form = await event.request.formData();
		const alias = String(form.get('alias') ?? '');
		const dspAddress = String(form.get('dsp_address') ?? '');
		if (!alias || !dspAddress) {
			return fail(400, { error: 'Promotion needs the organisation and its DSP address' });
		}
		try {
			await promoteOwner(session.accessToken ?? '', alias, { dsp_address: dspAddress });
		} catch (e) {
			return fail(502, { error: e instanceof Error ? e.message : 'Promotion failed' });
		}
		throw redirect(303, '/admin/onboarding?status=verified');
	},
};
