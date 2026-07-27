import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { hasGrant, requireGrant } from '$lib/server/auth';
import {
	createInvite,
	decideApplication,
	issueOrganizationCredential,
	listAgreements,
	listApplications,
	listInvites,
	listOwners,
	promoteOwner,
	recordAgreementAcceptance,
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
		const [applications, owners, agreements, invites] = await Promise.all([
			listApplications(token, status),
			listOwners(token).catch(() => []),
			listAgreements(token).catch(() => []),
			listInvites(token).catch(() => []),
		]);
		return {
			applications,
			owners,
			agreements,
			invites,
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
