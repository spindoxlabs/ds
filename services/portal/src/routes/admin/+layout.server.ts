import type { LayoutServerLoad } from './$types';
import { ADMIN_SECTION_GRANTS, requireGrant } from '$lib/server/auth';

/**
 * Gate the `/admin` section on the union of grants its pages need, not on full
 * admin. `requireAdmin` here refused an `ds-onboarding-operator` before the
 * onboarding and agreements pages could run their own `requireGrant`, making
 * that seat unusable. Each page still enforces its specific grant; this only
 * decides who may enter the section at all.
 */
export const load: LayoutServerLoad = async (event) => {
	const session = await requireGrant(event, ...ADMIN_SECTION_GRANTS);
	return { session };
};
