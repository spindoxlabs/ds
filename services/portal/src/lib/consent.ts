/**
 * Consent vocabulary shared by server loaders and browser components.
 *
 * Deliberately **not** under `$lib/server/`: components need these values at
 * runtime, and SvelteKit refuses a value import from a server module (a type-only
 * import is erased, a value import would ship server code to the browser).
 */

/**
 * A consent row whose `consumer_id` is this is a **scoped wildcard**: a standing
 * decision admitting any party inside the circle for that controller and purpose
 * — never a new controller or purpose. A per-party row overrides it, so an
 * explicit grant or opt-out still wins.
 *
 * It must not be rendered as a grant to one named party, which is what it looked
 * like before.
 */
export const WILDCARD_CONSUMER = '*';

/**
 * A purpose IRI or slug as a human label: `FlexibilityResearch` → `Flexibility
 * research`.
 *
 * Purposes cross the wire as taxonomy slugs (a consumer request record) or as
 * full profile IRIs (an ODRL policy), and both must render the same way. Lives
 * here rather than in `$lib/server/odrl` so the server summary and the browser
 * components share one implementation — two would drift, and a purpose label
 * that differs between the request form and the request record is exactly the
 * kind of difference that makes an audit record arguable.
 */
export function purposeLabel(value: string): string {
	const slug = value.split(/[/#:]/).pop() ?? value;
	const words = slug.replace(/([a-z0-9])([A-Z])/g, '$1 $2');
	return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
}
