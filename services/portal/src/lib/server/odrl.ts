/**
 * ODRL JSON-LD → plain-language sentences.
 * Used server-side in load functions; result passed as plain strings to components.
 *
 * Two JSON-LD shapes reach this module and both must render identically:
 * the dataset-api serves `odrl:`-prefixed terms, while the federated catalog
 * serves its own @context with the terms unprefixed (`permission`, `action`,
 * `leftOperand`). Reading only one shape silently produced an empty summary for
 * every federated dataset, so every lookup goes through `term()`.
 */

import { purposeLabel } from '$lib/consent';

interface OdrlAction {
	'@id'?: string;
}

type OdrlConstraint = Record<string, unknown>;

type OdrlRule = Record<string, unknown>;

/** Read an ODRL term under its prefixed or unprefixed name. */
function term<T = unknown>(obj: Record<string, unknown> | null | undefined, name: string): T | undefined {
	if (!obj) return undefined;
	return (obj[`odrl:${name}`] ?? obj[name]) as T | undefined;
}

export interface OfferPurpose {
	/** The IRI as published, which is what the connector validates. */
	iri: string;
	/** Human label derived from the IRI's last segment. */
	label: string;
}

export interface PolicySummary {
	permitted: string[];
	prohibited: string[];
	obligations: string[];
	constraints: string[];
	/**
	 * Every purpose the offer permits, as a list a person can choose from.
	 *
	 * `constraints` renders the same information as a sentence, which is right
	 * for reading and useless for choosing. A multi-purpose offer publishes one
	 * `odrl:purpose` constraint with `odrl:isAnyOf` over a list — the shape the
	 * ODRL Information Model prescribes for set-based operators — so this is a
	 * list, never a single value.
	 */
	purposes: OfferPurpose[];
}

/** Last path segment of an IRI, lowercased — the two sources differ in case
 *  (`.../policy/Query` vs `odrl:query`), and a case-sensitive lookup made the
 *  same policy render differently depending on where it was read from. */
function localName(iri: string): string {
	return (iri.split(/[/#:]/).pop() ?? iri).toLowerCase();
}

function actionLabel(action: OdrlAction | string | undefined): string {
	const id = typeof action === 'string' ? action : action?.['@id'] ?? '';
	const labels: Record<string, string> = {
		use: 'Use data',
		query: 'Execute queries',
		distribute: 'Distribute to third parties',
		modify: 'Modify data',
		reproduce: 'Copy / download',
		aggregate: 'Aggregate results',
		delete: 'Delete after retention period',
		anonymize: 'Anonymise before use',
		attribute: 'Attribute the data source',
	};
	// Fall back to the original segment, not the lowercased one — an unmapped
	// term should read as it was written.
	return labels[localName(id)] ?? (id.split(/[/#:]/).pop() ?? id);
}

function constraintSentence(c: OdrlConstraint): string {
	const rawLeft = term<string | { '@id': string }>(c, 'leftOperand');
	const left = typeof rawLeft === 'string' ? rawLeft : rawLeft?.['@id'] ?? '';
	const right = String(term<string>(c, 'rightOperand') ?? '');

	const map: Record<string, (r: string) => string> = {
		accessscope: (r) => `Requires OAuth scope "${r}"`,
		consentstatus: (r) => `Data-subject consent must be "${r}"`,
		contractrequired: (r) =>
			r === 'true' ? 'A bilateral contract agreement is required' : 'No contract required',
		participantrole: (r) => `Requesting participant must have role "${r}"`,
		purpose: (r) => `Declared purpose must be "${r}"`,
		membership: (r) => `Requester must be a member of "${r}"`,
	};
	const short = left.split(/[/#:]/).pop() ?? left;
	return map[localName(left)]?.(right) ?? `${short} = ${right}`;
}

function rulesFor(rules: OdrlRule | OdrlRule[] | undefined): OdrlRule[] {
	if (!rules) return [];
	return Array.isArray(rules) ? rules : [rules];
}

/** Every purpose IRI in a right operand — scalar (`isA`) or set (`isAnyOf`). */
function purposeValues(right: unknown): string[] {
	const items = Array.isArray(right) ? right : [right];
	const out: string[] = [];
	for (const item of items) {
		const value =
			typeof item === 'string'
				? item
				: ((item as Record<string, string>)?.['@id'] ??
					(item as Record<string, string>)?.['@value']);
		if (typeof value === 'string' && value && !out.includes(value)) out.push(value);
	}
	return out;
}

export function summarisePolicy(policy: Record<string, unknown> | null | undefined): PolicySummary {
	if (!policy)
		return { permitted: [], prohibited: [], obligations: [], constraints: [], purposes: [] };

	const perms = rulesFor(term<OdrlRule | OdrlRule[]>(policy, 'permission'));
	const prohbs = rulesFor(term<OdrlRule | OdrlRule[]>(policy, 'prohibition'));
	const obligs = rulesFor(term<OdrlRule | OdrlRule[]>(policy, 'obligation'));

	const labelOf = (r: OdrlRule) => actionLabel(term<OdrlAction | string>(r, 'action'));
	const permitted = perms.map(labelOf);
	const prohibited = prohbs.map(labelOf);
	const obligations = obligs.map(labelOf);

	const allRuleConstraints = [...perms, ...prohbs, ...obligs].flatMap((r) => {
		const c = term<OdrlConstraint | OdrlConstraint[]>(r, 'constraint');
		if (!c) return [];
		return Array.isArray(c) ? c : [c];
	});
	const constraints = [...new Set(allRuleConstraints.map(constraintSentence))];

	// Only a *permission*'s purposes are offered as a choice: a purpose named in
	// a prohibition is the one thing the consumer may not declare.
	const purposeIris = perms
		.flatMap((r) => {
			const c = term<OdrlConstraint | OdrlConstraint[]>(r, 'constraint');
			if (!c) return [];
			return Array.isArray(c) ? c : [c];
		})
		.filter((c) => {
			const rawLeft = term<string | { '@id': string }>(c, 'leftOperand');
			const left = typeof rawLeft === 'string' ? rawLeft : (rawLeft?.['@id'] ?? '');
			return localName(left) === 'purpose';
		})
		.flatMap((c) => purposeValues(term(c, 'rightOperand')));

	const purposes = [...new Set(purposeIris)].map((iri) => ({ iri, label: purposeLabel(iri) }));

	return { permitted, prohibited, obligations, constraints, purposes };
}
