import { describe, it, expect } from 'vitest';
import { ServiceError } from '../../src/lib/service-error';
import {
	custodianOf,
	custodyOf,
	explainSubjectFailure,
	participantLabel,
} from '../../src/lib/subject-problems';

const HERE = 'did:web:dso.example.org';
const REC = 'did:web:rec.example.org';
const MEMBER = `${REC}:users:ex-00001`;

function refusal(status: number, detail: string): ServiceError {
	return new ServiceError(status, 'http://connector.example.org/consent/my', JSON.stringify({ detail }));
}

describe('whose data this portal holds', () => {
	it('reads the custodian from the DID', () => {
		expect(custodianOf(MEMBER)).toBe(REC);
		expect(custodianOf('did:web:rec.example.org')).toBeNull();
		expect(custodianOf('did:key:z6Mk:users:x')).toBeNull();
	});

	it('is elsewhere only when both sides are known and differ', () => {
		expect(custodyOf(MEMBER, HERE).isHome).toBe(false);
		expect(custodyOf(MEMBER, REC).isHome).toBe(true);
		// Unknown either way keeps calling the connector, which explains itself.
		expect(custodyOf(MEMBER, undefined).isHome).toBe(true);
		expect(custodyOf('did:web:rec.example.org', HERE).isHome).toBe(true);
		expect(custodyOf('', HERE).isHome).toBe(true);
	});

	it('names a participant by its host’s first label', () => {
		expect(participantLabel(REC)).toBe('rec');
		expect(participantLabel('did:web:localhost%3A8443')).toBe('localhost');
		expect(participantLabel(null)).toBe('unknown');
	});
});

describe('what a subject page says when a call failed', () => {
	it('keeps the raw error for the technical block', () => {
		const e = refusal(503, 'down');
		expect(explainSubjectFailure('consents', e).technical).toBe(e.message);
	});

	it('says a credential from another participant is managed elsewhere', () => {
		const p = explainSubjectFailure('consents', refusal(403, 'User VC is not linked to this participant'));
		expect(p.tone).toBe('warning');
		expect(p.title).toMatch(/another organisation/);
	});

	it('asks to sign in again on 401', () => {
		expect(explainSubjectFailure('sharing', refusal(401, 'expired')).title).toMatch(/sign in/i);
	});

	it('treats an unreachable backend as an outage', () => {
		const p = explainSubjectFailure('activity', new TypeError('fetch failed'));
		expect(p.tone).toBe('error');
		expect(p.technical).toBe('fetch failed');
	});

	it('never puts the status or URL in the sentence a person reads', () => {
		for (const status of [400, 401, 403, 404, 409, 500, 503]) {
			const p = explainSubjectFailure('change', refusal(status, 'x'));
			expect(`${p.title} ${p.message}`).not.toMatch(/http|\b\d{3}\b/);
		}
	});
});
