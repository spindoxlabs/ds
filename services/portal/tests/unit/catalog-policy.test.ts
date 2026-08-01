import { describe, it, expect } from 'vitest';
import { datasetPolicy } from '../../src/lib/server/catalog';
import { summarisePolicy } from '../../src/lib/server/odrl';

const POLICY = {
	'@type': 'odrl:Set',
	'odrl:permission': [{ 'odrl:action': { '@id': 'odrl:query' } }],
};

describe('datasetPolicy', () => {
	it('reads a prefixed policy on the dataset', () => {
		expect(datasetPolicy({ 'odrl:hasPolicy': POLICY })).toEqual(POLICY);
	});

	it('reads an unprefixed policy on the first distribution', () => {
		const dataset = { distribution: [{ hasPolicy: POLICY }] };
		expect(datasetPolicy(dataset)).toEqual(POLICY);
	});

	it('unwraps a single-element policy array', () => {
		expect(datasetPolicy({ 'odrl:hasPolicy': [POLICY] })).toEqual(POLICY);
	});

	it('returns null when the record carries no policy', () => {
		expect(datasetPolicy({ '@id': 'urn:x' })).toBeNull();
		expect(datasetPolicy(null)).toBeNull();
	});

	it('feeds a real, non-empty summary (the consent page rendered nothing before)', () => {
		const summary = summarisePolicy(datasetPolicy({ 'odrl:hasPolicy': POLICY }));
		expect(summary.permitted).toContain('Execute queries');
	});
});
