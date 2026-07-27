import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

/**
 * Public organisation application.
 *
 * Deliberately **outside every auth guard**: an organisation applying to join has
 * no identity yet. The invite code the operator issued is the credential, and the
 * identity registry checks it — the portal never validates it locally, so this
 * page cannot become a way to probe which codes exist.
 *
 * Nothing here is trusted. It records a claim an operator verifies offline, and
 * `evidence_ref` is a reference to that evidence (a ticket or document id) — no
 * documents are uploaded or stored.
 */
export const load: PageServerLoad = async ({ url }) => {
	// A code may arrive in the invitation link; it is only a convenience.
	return { prefilledCode: url.searchParams.get('code') ?? '' };
};

export const actions: Actions = {
	default: async ({ request, fetch }) => {
		const form = await request.formData();
		const value = (name: string) => String(form.get(name) ?? '').trim();

		const body = {
			invite_code: value('invite_code'),
			alias: value('alias'),
			legal_name: value('legal_name'),
			registration_number: value('registration_number') || undefined,
			registration_type: value('registration_type') || undefined,
			legal_country_code: value('legal_country_code') || undefined,
			dsp_address: value('dsp_address') || undefined,
			evidence_ref: value('evidence_ref') || undefined,
			notes: value('notes') || undefined,
			roles: ['consumer'],
		};

		if (!body.invite_code || !body.alias || !body.legal_name) {
			return fail(400, { error: 'An invitation code, a short name and a legal name are required.', values: body });
		}

		const irUrl = env.IDENTITY_REGISTRY_URL ?? 'http://172.17.0.1:30005';
		try {
			const res = await fetch(`${irUrl}/onboarding/applications`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) {
				const detail = await res.json().catch(() => ({}));
				return fail(res.status, {
					error: String(detail.detail ?? 'The application could not be filed.'),
					values: body,
				});
			}
			const created = await res.json();
			return { submitted: true, alias: created.alias };
		} catch {
			return fail(502, { error: 'The registry is unreachable. Try again shortly.', values: body });
		}
	},
};
