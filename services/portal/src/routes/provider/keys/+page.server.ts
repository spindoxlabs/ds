import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { requireGrant } from '$lib/server/auth';
import {
	chooseOffer,
	chooseTab,
	explainFailure,
	holderPath,
	listableOffers,
	type HolderKeyEvents,
	type HolderKeys,
	type OfferSummary,
} from '$lib/holder-keys';

/**
 * Which data keys this participant serves, per offer, and their history.
 *
 * The holder's read of its own enforcement state (ADR-0022): a collector
 * registers its members' decisions here with their keys, and the data plane
 * serves by those keys. This page shows the keys — never who stands behind
 * them — to whoever the connector accepts as the holder: here, a person with
 * `connector.consent.holder.read` or the deployment operator. The connector
 * re-checks every call; this guard only explains a refusal up front.
 */
export const load: PageServerLoad = async (event) => {
	await event.parent(); // provider authority
	const session = await requireGrant(event, 'connector.consent.holder.read');
	const token = session?.accessToken ?? '';
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const { url, fetch } = event;

	let offers: OfferSummary[] = [];
	try {
		const res = await fetch(`${connectorUrl}/ns/sharing-offers`);
		if (!res.ok) throw new Error(String(res.status));
		offers = listableOffers((await res.json()) as OfferSummary[]);
	} catch (err) {
		return {
			offers,
			offerId: null,
			tab: chooseTab(url.searchParams.get('tab')),
			keys: null,
			history: null,
			error: `Could not read this connector's sharing offers (${String(err)}).`,
		};
	}

	const offerId = chooseOffer(offers, url.searchParams.get('offer'));
	const tab = chooseTab(url.searchParams.get('tab'));
	const base = { offers, offerId, tab, keys: null, history: null, error: null };
	if (!offerId) return base;

	const path = holderPath(tab, offerId, url.searchParams.get('cursor'));
	try {
		const res = await fetch(`${connectorUrl}${path}`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!res.ok) return { ...base, error: explainFailure(res.status, offerId) };
		const body = await res.json();
		return tab === 'history'
			? { ...base, history: body as HolderKeyEvents }
			: { ...base, keys: body as HolderKeys };
	} catch (err) {
		return { ...base, error: `Could not reach the connector (${String(err)}).` };
	}
};
