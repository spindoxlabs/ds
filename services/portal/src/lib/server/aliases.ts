/**
 * Layer B group aliases for the portal, read from the environment.
 *
 * A deployment whose realm names groups its own way maps them onto ds bundles
 * with `PORTAL_OIDC_GROUP_ALIASES` — the same JSON contract every ds service
 * takes as `<SERVICE>_OIDC_GROUP_ALIASES`. The rulebook is emphatic that this be
 * set on **every** service: a half-wired map is a deployment where authority
 * depends on which service answered. Parsing (and its bundle-only validation)
 * lives in the generated twin so it cannot drift from `ds_auth`.
 */
import { env } from '$env/dynamic/private';
import { parseGroupAliases } from './bundles.generated';

let cached: Record<string, string> | null = null;

/** The parsed alias map, computed once. */
export function groupAliases(): Record<string, string> {
	if (cached === null) cached = parseGroupAliases(env.PORTAL_OIDC_GROUP_ALIASES);
	return cached;
}
