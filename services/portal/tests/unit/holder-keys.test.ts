import { describe, it, expect } from 'vitest';
import {
	chooseOffer,
	chooseTab,
	explainFailure,
	holderPath,
	listableOffers,
	pageHref,
	plainList,
	type HolderKey,
	type OfferSummary,
} from '../../src/lib/holder-keys';

function offer(id: string, extra: Partial<OfferSummary> = {}): OfferSummary {
	return {
		id,
		purpose: 'EnergyCommunityOperation',
		requires_consent: true,
		recipients: { recipient: 'example-rec' },
		dataset_count: 1,
		...extra,
	};
}

function key(value: string, dataset = 'ds.readings'): HolderKey {
	return { dataset_id: dataset, key: `pod:${value}`, key_type: 'pod', value, authorised_since: null };
}

describe('the offers the page lists', () => {
	it('keeps consent-based offers backed by a dataset here, sorted', () => {
		const listed = listableOffers([
			offer('release-b'),
			offer('contract', { requires_consent: false }),
			offer('elsewhere', { dataset_count: 0 }),
			offer('release-a'),
		]);
		expect(listed.map((o) => o.id)).toEqual(['release-a', 'release-b']);
	});

	it('honours the asked offer only when it is listable', () => {
		const offers = [offer('a'), offer('b')];
		expect(chooseOffer(offers, 'b')).toBe('b');
		expect(chooseOffer(offers, 'not-here')).toBe('a');
		expect(chooseOffer(offers, null)).toBe('a');
		expect(chooseOffer([], 'a')).toBeNull();
	});
});

describe('the connector call', () => {
	it('reads the key list for the current tab, and the history for the other', () => {
		expect(holderPath('current', 'release', null)).toBe(
			'/consent/admin/holder/keys?offer_id=release',
		);
		expect(holderPath('history', 'release', 'abc', '2026-10-01T00:00:00Z')).toBe(
			'/consent/admin/holder/key-events?offer_id=release&cursor=abc&since=2026-10-01T00%3A00%3A00Z',
		);
	});

	it('defaults to the current tab', () => {
		expect(chooseTab(null)).toBe('current');
		expect(chooseTab('anything')).toBe('current');
		expect(chooseTab('history')).toBe('history');
	});

	it('keeps the page state in the URL', () => {
		expect(pageHref('release', 'history', 'c1')).toBe('?offer=release&tab=history&cursor=c1');
	});
});

describe('handing the list on', () => {
	it('gives each value once, one per line, without the type', () => {
		expect(plainList([key('EX01'), key('EX02'), key('EX01', 'ds.other')])).toBe('EX01\nEX02');
	});
});

describe('a refusal names its cause', () => {
	it('says what each answer means', () => {
		expect(explainFailure(403, 'r')).toContain('connector.consent.holder.read');
		expect(explainFailure(422, 'r')).toContain('serves no dataset');
		expect(explainFailure(409, 'r')).toContain('not consent-based');
		expect(explainFailure(503, 'r')).toContain('recipient');
		expect(explainFailure(500, 'r')).toContain('500');
	});
});
