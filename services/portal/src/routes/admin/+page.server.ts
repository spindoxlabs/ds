import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { hasGrant } from '$lib/server/auth';
import { queryEvents, type AuditEntry } from '$lib/server/provenance';

/**
 * The operator landing answers "is this instance healthy, and what has it been
 * doing" — not "here are some links". A panel of static cards tells an operator
 * nothing they could act on.
 *
 * Every upstream is optional: one unreachable service degrades its own tile
 * rather than emptying the page, because the page exists precisely to show that
 * something is down.
 */
export const load: PageServerLoad = async ({ locals, fetch, parent }) => {
	await parent(); // the layout guard establishes operator authority
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

	const count = async (path: string): Promise<number | null> => {
		try {
			const res = await fetch(`${connectorUrl}${path}`, { headers: authHeaders });
			if (!res.ok) return null;
			const body = await res.json();
			if (Array.isArray(body)) return body.length;
			if (Array.isArray(body?.datasets)) return body.datasets.length;
			return null;
		} catch {
			return null;
		}
	};

	const [participants, assets, agreements] = await Promise.all([
		count('/admin/participants'),
		count('/provider/assets'),
		count('/history/agreements'),
	]);

	let recentEvents: AuditEntry[] = [];
	let eventsError: string | null = null;
	try {
		recentEvents = (await queryEvents({ limit: 8 }, token)).events;
	} catch (e) {
		eventsError = e instanceof Error ? e.message : 'Provenance is unavailable';
	}

	return {
		counts: { participants, assets, agreements },
		recentEvents,
		eventsError,
		// Drives which management actions are offered. The API re-authorizes
		// regardless; this only avoids showing a button that would 403.
		may: {
			manageParticipants: hasGrant(session, 'identity-registry.admin'),
			syncGovernance: hasGrant(session, 'connector.provider.write'),
		},
	};
};
