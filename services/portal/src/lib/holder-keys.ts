/**
 * The holder's key list and history (ADR-0022) — the logic the page needs,
 * kept out of the component so it can be tested without a stack.
 *
 * The connector answers `GET /consent/admin/holder/keys` (the keys this
 * participant's data plane serves an offer's recipient now) and
 * `GET /consent/admin/holder/key-events` (every key a decision started or
 * stopped carrying). Both are keys only: no subject is ever in them.
 */

export interface OfferSummary {
	id: string;
	purpose: string;
	requires_consent: boolean;
	recipients: { recipient: string; recipient_role?: string | null };
	dataset_count: number;
}

export interface HolderKey {
	dataset_id: string;
	key: string;
	key_type: string;
	value: string;
	authorised_since: string | null;
}

export interface HolderKeys {
	offer_id: string;
	recipient: string;
	recipient_did: string;
	purpose: string[];
	recipient_role: string | null;
	datasets: { dataset_id: string; key_count: number; grants_without_keys: boolean }[];
	limit: number;
	keys: HolderKey[];
	next_cursor: string | null;
}

export interface HolderKeyEvent {
	dataset_id: string;
	consumer_id: string;
	key: string;
	event: 'added' | 'removed';
	cause: 'grant' | 'withdrawal' | 'key_change' | 'backfill';
	at: string;
	decided_by: string | null;
	collector: string | null;
}

export interface HolderKeyEvents {
	offer_id: string;
	datasets: string[];
	limit: number;
	note: string;
	events: HolderKeyEvent[];
	next_cursor: string | null;
}

export type Tab = 'current' | 'history';

/** Only consent-based offers backed by some dataset here can have keys. */
export function listableOffers(offers: OfferSummary[]): OfferSummary[] {
	return offers
		.filter((o) => o.requires_consent && o.dataset_count > 0)
		.sort((a, b) => a.id.localeCompare(b.id));
}

/** The offer asked for, when it is listable; otherwise the first listable. */
export function chooseOffer(offers: OfferSummary[], asked: string | null): string | null {
	if (asked && offers.some((o) => o.id === asked)) return asked;
	return offers[0]?.id ?? null;
}

export function chooseTab(asked: string | null): Tab {
	return asked === 'history' ? 'history' : 'current';
}

/** The connector path for a tab, with the page's query carried over. */
export function holderPath(
	tab: Tab,
	offerId: string,
	cursor: string | null,
	since: string | null = null,
): string {
	const params = new URLSearchParams({ offer_id: offerId });
	if (cursor) params.set('cursor', cursor);
	if (tab === 'history' && since) params.set('since', since);
	const route = tab === 'history' ? 'key-events' : 'keys';
	return `/consent/admin/holder/${route}?${params.toString()}`;
}

/** The page link for another tab, offer or page — the URL is the state. */
export function pageHref(offerId: string, tab: Tab, cursor: string | null = null): string {
	const params = new URLSearchParams({ offer: offerId, tab });
	if (cursor) params.set('cursor', cursor);
	return `?${params.toString()}`;
}

const CAUSE_LABELS: Record<HolderKeyEvent['cause'], string> = {
	grant: 'consent granted',
	withdrawal: 'consent withdrawn',
	key_change: 'keys re-registered',
	backfill: 'granted before history began',
};

export function causeLabel(cause: HolderKeyEvent['cause']): string {
	return CAUSE_LABELS[cause] ?? cause;
}

/** One value per line, for handing the list on: the values only, no type. */
export function plainList(keys: HolderKey[]): string {
	return [...new Set(keys.map((k) => k.value))].join('\n');
}

/** Why the connector refused, in words an operator can act on. */
export function explainFailure(status: number, offerId: string): string {
	switch (status) {
		case 403:
			return (
				'This connector refused the read. The key list is for this participant ' +
				'only: its own organisation, a deployment operator, or a person granted ' +
				'connector.consent.holder.read for it.'
			);
		case 409:
			return `Offer “${offerId}” is not consent-based, so no key is registered under it.`;
		case 422:
			return `This connector serves no dataset under offer “${offerId}”.`;
		case 503:
			return (
				'The connector cannot resolve this offer’s recipient right now, so it cannot ' +
				'say which keys it serves them. Try again shortly.'
			);
		default:
			return `The connector answered ${status}.`;
	}
}
