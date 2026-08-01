import { describe, it, expect, beforeAll, afterEach } from 'vitest';
import {
	SignJWT,
	generateKeyPair,
	exportJWK,
	createLocalJWKSet,
	type JWTVerifyGetKey,
	type KeyObject,
} from 'jose';
import { verifyToken, resolveIssuer } from '../../src/lib/server/token';

const ISSUER = 'http://keycloak.dataspaces.localhost/realms/dataspaces';
const KID = 'test-key-1';

let privateKey: KeyObject;
let jwks: JWTVerifyGetKey;
/** A second, unrelated key — its tokens are validly signed but by a key the JWKS does not carry. */
let strangerKey: KeyObject;

async function sign(
	key: KeyObject,
	claims: Record<string, unknown>,
	{ issuer = ISSUER, expiresIn = '1h', setExp = true, kid = KID } = {},
): Promise<string> {
	let jwt = new SignJWT(claims).setProtectedHeader({ alg: 'RS256', kid }).setIssuedAt().setIssuer(issuer);
	if (setExp) jwt = jwt.setExpirationTime(expiresIn);
	return jwt.sign(key);
}

beforeAll(async () => {
	const pair = await generateKeyPair('RS256');
	privateKey = pair.privateKey as KeyObject;
	const publicJwk = await exportJWK(pair.publicKey);
	jwks = createLocalJWKSet({ keys: [{ ...publicJwk, kid: KID, alg: 'RS256', use: 'sig' }] });
	strangerKey = (await generateKeyPair('RS256')).privateKey as KeyObject;
});

describe('verifyToken', () => {
	it('accepts a properly signed, unexpired token from the expected issuer', async () => {
		const token = await sign(privateKey, { email: 'subject@example.test', name: 'Real' });
		const claims = await verifyToken(token, jwks, ISSUER);
		expect(claims).not.toBeNull();
		expect(claims?.email).toBe('subject@example.test');
	});

	// The defect this whole row exists for: an unsigned JWT (the old code
	// base64-decoded the payload and trusted it) must not authenticate anyone.
	it('rejects an unsigned token whose payload names a real user', async () => {
		const b64 = (o: unknown) =>
			Buffer.from(JSON.stringify(o)).toString('base64url');
		const header = b64({ alg: 'none', typ: 'JWT' });
		const payload = b64({ email: 'subject@example.test', exp: Math.floor(Date.now() / 1000) + 3600, iss: ISSUER });
		const unsigned = `${header}.${payload}.`;
		expect(await verifyToken(unsigned, jwks, ISSUER)).toBeNull();
	});

	it('rejects a token whose payload was tampered with after signing', async () => {
		const token = await sign(privateKey, { email: 'subject@example.test' });
		const [h, , s] = token.split('.');
		const forged = Buffer.from(JSON.stringify({ email: 'admin@example.test', iss: ISSUER })).toString('base64url');
		expect(await verifyToken(`${h}.${forged}.${s}`, jwks, ISSUER)).toBeNull();
	});

	it('rejects a token signed by a key the JWKS does not carry', async () => {
		const token = await sign(strangerKey, { email: 'subject@example.test' });
		expect(await verifyToken(token, jwks, ISSUER)).toBeNull();
	});

	it('rejects a token minted by a different issuer', async () => {
		const token = await sign(privateKey, { email: 'subject@example.test' }, { issuer: 'http://evil.example/realms/x' });
		expect(await verifyToken(token, jwks, ISSUER)).toBeNull();
	});

	it('rejects an expired token', async () => {
		const token = await sign(privateKey, { email: 'subject@example.test' }, { expiresIn: '-1h' });
		expect(await verifyToken(token, jwks, ISSUER)).toBeNull();
	});

	it('rejects a token with no exp claim', async () => {
		const token = await sign(privateKey, { email: 'subject@example.test' }, { setExp: false });
		expect(await verifyToken(token, jwks, ISSUER)).toBeNull();
	});
});

describe('resolveIssuer', () => {
	const saved = process.env.KEYCLOAK_ISSUER_URL;
	afterEach(() => {
		if (saved === undefined) delete process.env.KEYCLOAK_ISSUER_URL;
		else process.env.KEYCLOAK_ISSUER_URL = saved;
	});

	it('throws when KEYCLOAK_ISSUER_URL is unset (no silent compose fallback)', () => {
		delete process.env.KEYCLOAK_ISSUER_URL;
		expect(() => resolveIssuer()).toThrow(/KEYCLOAK_ISSUER_URL/);
	});

	it('returns the issuer without a trailing slash', () => {
		process.env.KEYCLOAK_ISSUER_URL = 'https://kc.example/realms/dataspaces/';
		expect(resolveIssuer()).toBe('https://kc.example/realms/dataspaces');
	});
});
