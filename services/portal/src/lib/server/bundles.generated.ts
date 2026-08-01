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
 * `ds_auth.bundles.expand_bundles`. Four rules, in order: a Layer B alias is
 * translated first (a foreign IdP's group name becomes the ds bundle a
 * deployment mapped it to); a known bundle expands; a machine-identity
 * permission is dropped (never grantable to a human, however the group is
 * named); anything else passes through verbatim, so a realm still carrying the
 * old scope-named groups keeps working.
 */
export function expandBundles(
	groups: Iterable<string>,
	aliases: Record<string, string> = {},
): string[] {
	const seen = new Set<string>();
	const result: string[] = [];
	const machine = new Set(MACHINE_IDENTITY_PERMISSIONS);

	const add = (permission: string) => {
		if (permission && !seen.has(permission)) {
			seen.add(permission);
			result.push(permission);
		}
	};

	for (const raw of groups) {
		if (typeof raw !== 'string' || !raw) continue;
		// Rule 0: translate a foreign name before anything else looks at it.
		const group = aliases[raw] ?? raw;
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

/**
 * Parse and **validate** a Layer B alias map from its JSON env form — the twin
 * of `ds_auth.bundles.parse_group_aliases`. Aliases may only name bundles, never
 * capabilities, so deployment configuration cannot become a permission table:
 * an entry whose target is not a known bundle is dropped (and warned), and
 * malformed JSON yields an empty map rather than a silently different one.
 */
export function parseGroupAliases(raw: string | null | undefined): Record<string, string> {
	if (!raw || !raw.trim()) return {};

	let parsed: unknown;
	try {
		parsed = JSON.parse(raw);
	} catch (e) {
		console.error(`[ds-portal] group alias map is not valid JSON — no aliases applied: ${e}`);
		return {};
	}
	if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
		console.error('[ds-portal] group alias map must be a JSON object — no aliases applied.');
		return {};
	}

	const aliases: Record<string, string> = {};
	for (const [foreign, target] of Object.entries(parsed as Record<string, unknown>)) {
		if (typeof target !== 'string') {
			console.error(`[ds-portal] ignoring non-string alias entry ${foreign} -> ${String(target)}`);
			continue;
		}
		if (!(target in ROLE_BUNDLES)) {
			console.error(
				`[ds-portal] ignoring alias ${foreign} -> ${target}: not a role bundle. ` +
					`An alias may only name a bundle (${Object.keys(ROLE_BUNDLES).sort().join(', ')}).`,
			);
			continue;
		}
		aliases[foreign] = target;
	}
	return aliases;
}
