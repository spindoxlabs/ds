import { env } from '$env/dynamic/private';
import { resolveIssuer } from './token';

function identityRegistryUrl(): string {
	return env.IDENTITY_REGISTRY_URL ?? 'http://172.17.0.1:30005';
}

/**
 * This participant's **own** registry — where the credentials of the people it
 * onboarded are held (`DID-11` step 2).
 *
 * Two different questions with two different owners: *who is this person* is
 * registry data and stays at the trust anchor above; *what credentials do they
 * hold* is custody, and after `D-49`/`D-50` that is the organisation's own
 * instance. Falls back to the anchor so a single-instance deployment still
 * works — and the fallback is why this is a function rather than a constant:
 * the two URLs are the same value in dev-before-the-split and different
 * everywhere else.
 */
function participantRegistryUrl(): string {
	return env.PARTICIPANT_IDENTITY_REGISTRY_URL ?? identityRegistryUrl();
}

let cachedToken: { token: string; expiresAt: number } | null = null;
let warnedDefaultSecret = false;

// Client id/secret come from env; the in-code defaults keep local dev working.
// Using the default secret is insecure, so warn (once) when it falls back.
const DEFAULT_SERVICE_CLIENT = 'svc-ds-portal';

async function getServiceToken(): Promise<string> {
	if (cachedToken && cachedToken.expiresAt > Date.now() + 30_000) {
		return cachedToken.token;
	}

	// No compose-shaped fallback: an unset issuer under Helm used to default to a
	// dev URL, so the service token was requested from the wrong realm and every
	// VC-gated route silently bounced to `/`. Fail loudly instead.
	const issuer = resolveIssuer();
	const tokenUrl = `${issuer}/protocol/openid-connect/token`;
	const clientId = env.PORTAL_SERVICE_CLIENT_ID ?? DEFAULT_SERVICE_CLIENT;
	const clientSecret = env.PORTAL_SERVICE_CLIENT_SECRET ?? DEFAULT_SERVICE_CLIENT;

	if (!env.PORTAL_SERVICE_CLIENT_SECRET && !warnedDefaultSecret) {
		warnedDefaultSecret = true;
		console.warn(
			`[ds-portal] PORTAL_SERVICE_CLIENT_SECRET is not set — using the insecure ` +
				`default secret for client "${clientId}". Set a real secret in production.`,
		);
	}

	try {
		const res = await fetch(tokenUrl, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({
				grant_type: 'client_credentials',
				client_id: clientId,
				client_secret: clientSecret,
			}),
		});
		if (!res.ok) {
			console.error(`Service token request failed: ${res.status}`);
			return '';
		}
		const data = (await res.json()) as { access_token: string; expires_in: number };
		cachedToken = { token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
		return cachedToken.token;
	} catch (e) {
		console.error('Failed to acquire service token:', e);
		return '';
	}
}

export interface ResolvedCredential {
	role: string | null;
	vcJws: string | null;
}

export interface ResolvedIdentity {
	did: string;
	/** Every role the user holds — see `Session.userVcRoles`. */
	roles: string[];
	/** VC-JWS per role, for selecting the credential a call requires. */
	jwsByRole: Record<string, string>;
	/** Newest credential. Kept for callers with no role preference. */
	role: string | null;
	vcJws: string | null;
	subjectId: string;
}

export async function resolveUserByEmail(email: string): Promise<ResolvedIdentity | null> {
	if (!email) return null;
	const serviceToken = await getServiceToken();
	if (!serviceToken) return null;

	const url = `${identityRegistryUrl()}/users/resolve?email=${encodeURIComponent(email.trim().toLowerCase())}`;
	try {
		const res = await fetch(url, {
			headers: { Authorization: `Bearer ${serviceToken}` },
		});
		if (res.status === 404) return null;
		if (!res.ok) {
			console.error(`identity-registry /users/resolve failed: ${res.status}`);
			return null;
		}
		const data = (await res.json()) as {
			did: string;
			roles?: string[] | null;
			credentials?: Array<{ role?: string | null; vc_jws?: string | null }> | null;
			role?: string | null;
			vc_jws?: string | null;
			subject_id: string;
		};

		// **Credentials come from the custodian, identity from the anchor.**
		// The anchor answers with what it *issued* — it is the issuer, so it has
		// a copy — and reading them from there would make the split cosmetic:
		// this organisation would be presenting credentials it does not hold.
		// A custodian that has not received them yet is a real state and shows
		// as no roles, rather than as the issuer's copy standing in.
		const held = await credentialsHeldFor(data.did, serviceToken);
		const source = held ?? data;

		// `credentials` is ordered newest-first by the registry. Keep the first
		// JWS per role so a re-issued credential does not shadow the current one.
		const jwsByRole: Record<string, string> = {};
		for (const cred of source.credentials ?? []) {
			if (cred.role && cred.vc_jws && !(cred.role in jwsByRole)) {
				jwsByRole[cred.role] = cred.vc_jws;
			}
		}

		return {
			did: data.did,
			roles: source.roles ?? (source.role ? [source.role] : []),
			jwsByRole,
			role: source.role ?? null,
			vcJws: source.vc_jws ?? null,
			// The **anchor's**: the subject id is registry data, and the
			// custodian's copy of the credential does not carry the mapping.
			subjectId: data.subject_id,
		};
	} catch (e) {
		console.error('identity-registry unreachable:', e);
		return null;
	}
}

interface HeldCredentials {
	roles?: string[] | null;
	credentials?: Array<{ role?: string | null; vc_jws?: string | null }> | null;
	role?: string | null;
	vc_jws?: string | null;
}

/** The organisation a person's DID is filed under — `did:web:<custodian>:users:<id>`. */
function custodianOf(did: string): string | null {
	const marker = ':users:';
	const at = did.lastIndexOf(marker);
	return at === -1 || !did.startsWith('did:web:') ? null : did.slice(0, at);
}

/**
 * What this participant holds for a person — `GET /users/{did}/credentials`.
 *
 * **Only asked when this participant is that person's custodian**, and that
 * condition is the whole correctness of it. A person is filed under the
 * organisation that onboarded them (`DID-11` step 2), and an instance that is
 * not the custodian answers *"I hold nothing"* — which is true, and is not the
 * same as *"they hold nothing"*. Reading it as authoritative logged every
 * consumer out of this portal: their credentials live at their own
 * organisation's registry, this one legitimately had none, and the empty answer
 * replaced the anchor's record.
 *
 * Returns `null` when this participant is not the custodian or cannot answer,
 * and the caller then reads the anchor's issuance record.
 */
async function credentialsHeldFor(
	did: string,
	serviceToken: string,
): Promise<HeldCredentials | null> {
	const base = participantRegistryUrl();
	if (base === identityRegistryUrl()) return null;

	const own = env.PARTICIPANT_DID;
	if (!own || custodianOf(did) !== own) return null;
	try {
		const res = await fetch(`${base}/users/${encodeURIComponent(did)}/credentials`, {
			headers: { Authorization: `Bearer ${serviceToken}` },
		});
		if (!res.ok) {
			if (res.status !== 404) {
				console.error(`participant /users/{did}/credentials failed: ${res.status}`);
			}
			return null;
		}
		return (await res.json()) as HeldCredentials;
	} catch (e) {
		console.error('participant identity-registry unreachable:', e);
		return null;
	}
}

// ── Organisation onboarding (operator console) ────────────────────────────────
//
// These forward the **operator's own token**, not the portal service account.
// `svc-ds-portal` deliberately holds no onboarding grant: admin is an operator
// grant, and a long-lived process should not carry it (see `clients.yaml`). So a
// 403 here means the signed-in user lacks the Keycloak group, which is a fact
// worth showing them rather than hiding.
//
// Every call is the same endpoint `ir-cli` uses. The CLI stays the reference
// implementation — the console must not become a second way to change trust
// state.

export interface OrganizationApplication {
	id: string;
	alias: string;
	legal_name: string;
	registration_number?: string | null;
	registration_type?: string | null;
	hq_country_code?: string | null;
	legal_country_code?: string | null;
	roles: string[];
	did?: string | null;
	dsp_address?: string | null;
	status: 'pending' | 'verified' | 'rejected';
	evidence_ref?: string | null;
	verified_by?: string | null;
	verified_at?: string | null;
	notes?: string | null;
	created_at: string;
	updated_at: string;
}

export interface Owner {
	id: string;
	name?: string | null;
	did?: string | null;
	status?: string | null;
	agreement_id?: string | null;
	agreement_version?: string | null;
	agreement_capacity?: string | null;
	agreement_accepted_at?: string | null;
}

export interface Agreement {
	id: string;
	version: string;
	title?: string | null;
	capacity?: string | null;
	texts?: Record<string, unknown>;
	created_at?: string;
	updated_at?: string;
}

export interface AgreementAcceptance {
	agreement_id: string;
	version: string;
	owner_alias: string;
	locale?: string | null;
	accepted_by?: string | null;
	accepted_at?: string;
}

async function irFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
	const res = await fetch(`${identityRegistryUrl()}${path}`, {
		...init,
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`,
			...((init.headers as Record<string, string>) ?? {}),
		},
	});
	if (!res.ok) {
		const body = await res.text().catch(() => res.statusText);
		throw new Error(`${res.status} ${path}: ${body}`);
	}
	if (res.status === 204) return undefined as T;
	return (await res.json()) as T;
}

export function listApplications(token: string, status?: string) {
	const qs = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : '';
	return irFetch<OrganizationApplication[]>(`/admin/organizations/applications${qs}`, token);
}

export function listOwners(token: string) {
	return irFetch<Owner[]>('/admin/owners', token);
}

/** Verify or reject. `verified_by` is required by IR when moving to `verified`. */
export function decideApplication(
	token: string,
	id: string,
	body: { status: 'verified' | 'rejected'; verified_by?: string; evidence_ref?: string; notes?: string },
) {
	return irFetch<OrganizationApplication>(`/admin/organizations/applications/${id}`, token, {
		method: 'PATCH',
		body: JSON.stringify(body),
	});
}

/**
 * The DIDs that have **enrolled** — every registered participant.
 *
 * An organisation proves its own key since `DID-09`: the anchor mints nothing,
 * so a `did:web` an operator assigned is not yet an identity anybody can issue
 * to. This is how the console tells the two apart, and why the page can say
 * *"awaiting enrolment"* instead of offering a button that 409s.
 */
export async function listParticipantDids(token: string): Promise<string[]> {
	try {
		const body = await irFetch<unknown>('/admin/participants', token);
		const rows = Array.isArray(body)
			? body
			: ((body as { participants?: unknown[] })?.participants ?? []);
		return rows
			.map((r) => (r as { did?: string }).did)
			.filter((d): d is string => typeof d === 'string');
	} catch {
		// Not fatal: the page degrades to offering the action and letting the
		// registry refuse, which is what it did before this existed.
		return [];
	}
}

/** Gated by IR: the owner must be verified **and** hold a current agreement. */
export function issueOrganizationCredential(token: string, alias: string) {
	return irFetch<Record<string, unknown>>('/admin/credentials/organization', token, {
		method: 'POST',
		body: JSON.stringify({ alias }),
	});
}

/** Gated by IR: a valid, unrevoked OrganizationCredential must exist. */
export function promoteOwner(
	token: string,
	alias: string,
	body: { dsp_address: string; roles?: string[]; allowed_scopes?: string[] },
) {
	return irFetch<Record<string, unknown>>(`/admin/owners/${alias}/promote`, token, {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

export function recordAgreementAcceptance(
	token: string,
	alias: string,
	body: { agreement_id: string; version: string; locale?: string; accepted_by?: string },
) {
	return irFetch<Record<string, unknown>>(`/admin/owners/${alias}/agreement`, token, {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

export function listAgreements(token: string) {
	return irFetch<Agreement[]>('/agreements', token);
}

export function listAcceptances(token: string, agreementId: string) {
	return irFetch<AgreementAcceptance[]>(
		`/agreements/${encodeURIComponent(agreementId)}/acceptances`,
		token,
	);
}

export interface Invite {
	id: string;
	label?: string | null;
	created_by?: string | null;
	created_at: string;
	expires_at?: string | null;
	redeemed_at?: string | null;
	application_id?: string | null;
}

export interface IssuedInvite extends Invite {
	/** Returned once, at issue time. The registry stores only a hash. */
	code: string;
}

/**
 * Set an owner's `did:web`, which the credential gate requires.
 *
 * An organisation applying through the public route usually has no DID yet — it
 * is standing up a deployment, not migrating one — so the operator assigns it
 * here. Without this the gate can never be satisfied from the portal, and the
 * whole join flow dead-ends at "has no DID".
 */
export function updateOwner(token: string, alias: string, body: { did?: string }) {
	return irFetch<Owner>(`/admin/owners/${alias}`, token, {
		method: 'PATCH',
		body: JSON.stringify(body),
	});
}

export function listInvites(token: string) {
	return irFetch<Invite[]>('/admin/onboarding/invites', token);
}

export function createInvite(token: string, body: { label?: string; ttl_days?: number }) {
	return irFetch<IssuedInvite>('/admin/onboarding/invites', token, {
		method: 'POST',
		body: JSON.stringify(body),
	});
}

/**
 * The bundle a verified organisation stands its own deployment up from.
 *
 * **It carries no identity of ours** (`DID-10`). It used to return an STS client
 * secret the registry had minted, and generating one *rotated* that secret — so
 * any earlier bundle stopped working. Nothing here mints a secret now: the
 * recipient generates its own key and proves control of it, and the two secrets
 * it needs are named in the rendered config and left empty.
 *
 * What it does carry is a **single-use enrolment code**. Reissuing produces
 * another code and does not invalidate the first, so "send it again" is no
 * longer destructive — but it is also not revocation, and a UI should say so.
 */
export interface ProvisioningBundle {
	bundle: Record<string, unknown>;
	/** `.env` for the third party's deployment. **Contains the enrolment code.** */
	env: string;
	/** EDC `.properties`. Secret-free by construction — see `provisioning.py`. */
	properties: string;
}

export function generateProvisioningBundle(token: string, alias: string) {
	// `format=all` in one call: each call issues a *new* single-use enrolment
	// code, so fetching the three artefacts separately would hand over three
	// codes where the recipient needs one.
	return irFetch<ProvisioningBundle>(
		`/admin/owners/${alias}/provisioning-bundle?format=all`,
		token,
		{ method: 'POST' },
	);
}
