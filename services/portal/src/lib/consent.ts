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
