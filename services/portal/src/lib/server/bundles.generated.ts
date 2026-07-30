// GENERATED FILE — DO NOT EDIT.
//
// Source: libs/ds-auth/src/ds_auth/bundles.py
// Regenerate: task -d libs/ds-auth bundles:generate
//
// The role bundles a user token's groups are expanded through, mirroring
// `ds_auth.bundles` exactly. The portal gates its UI on the result; the backend
// re-authorizes every request against the same table, so a stale copy here shows
// the wrong buttons rather than granting anything.


export const ROLE_BUNDLES: Record<string, string[]> = {
	'ds-admin': [
		'identity-registry.admin',
		'connector.admin',
		'provenance.read',
		'provenance.write',
		'catalog.read',
	],
	'ds-member': [
		'catalog.read',
	],
	'ds-onboarding-operator': [
		'identity-registry.organizations.read',
		'identity-registry.organizations.write',
		'identity-registry.agreements.read',
		'identity-registry.participants.write',
		'identity-registry.read',
	],
	'ds-participant-admin': [
		'connector.provider.read',
		'connector.provider.write',
		'connector.history.read',
		'connector.registry.invalidate',
		'connector.consent.provision',
		'connector.ingestion.record',
		'catalog.read',
		'provenance.read',
		'identity-registry.read',
		'identity-registry.membership.read',
	],
	'ds-participant-viewer': [
		'connector.provider.read',
		'connector.history.read',
		'catalog.read',
		'provenance.read',
		'identity-registry.read',
	],
};

export const MACHINE_IDENTITY_PERMISSIONS: string[] = [
	'connector.internal',
	'connector.webhook',
];

/**
 * Expand role bundles into capabilities — the TypeScript twin of
 * `ds_auth.bundles.expand_bundles`. Three rules, in order: a known bundle
 * expands; a machine-identity permission is dropped (never grantable to a
 * human, however the group is named); anything else passes through verbatim, so
 * a realm still carrying the old scope-named groups keeps working.
 */
export function expandBundles(groups: Iterable<string>): string[] {
	const seen = new Set<string>();
	const result: string[] = [];
	const machine = new Set(MACHINE_IDENTITY_PERMISSIONS);

	const add = (permission: string) => {
		if (permission && !seen.has(permission)) {
			seen.add(permission);
			result.push(permission);
		}
	};

	for (const group of groups) {
		if (typeof group !== 'string' || !group) continue;
		const capabilities = ROLE_BUNDLES[group];
		if (capabilities) {
			for (const capability of capabilities) add(capability);
		} else if (machine.has(group)) {
			continue;
		} else {
			add(group);
		}
	}

	return result;
}
