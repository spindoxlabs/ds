/**
 * ODRL JSON-LD → plain-language sentences.
 * Used server-side in load functions; result passed as plain strings to components.
 */

interface OdrlAction {
	'@id'?: string;
}

interface OdrlConstraint {
	'odrl:leftOperand'?: string | { '@id': string };
	'odrl:rightOperand'?: string;
}

interface OdrlRule {
	'odrl:action'?: OdrlAction | string;
	'odrl:constraint'?: OdrlConstraint | OdrlConstraint[];
}

export interface PolicySummary {
	permitted: string[];
	prohibited: string[];
	obligations: string[];
	constraints: string[];
}

function actionLabel(action: OdrlAction | string | undefined): string {
	const id = typeof action === 'string' ? action : action?.['@id'] ?? '';
	const short = id.split(/[/#:]/).pop() ?? id;
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
	return labels[short] ?? short;
}

function constraintSentence(c: OdrlConstraint): string {
	const left =
		typeof c['odrl:leftOperand'] === 'string'
			? c['odrl:leftOperand']
			: c['odrl:leftOperand']?.['@id'] ?? '';
	const right = c['odrl:rightOperand'] ?? '';
	const short = left.split(/[/#:]/).pop() ?? left;

	const map: Record<string, (r: string) => string> = {
		accessScope: (r) => `Requires OAuth scope "${r}"`,
		consentStatus: (r) => `Data-subject consent must be "${r}"`,
		contractRequired: (r) =>
			r === 'true' ? 'A bilateral contract agreement is required' : 'No contract required',
		participantRole: (r) => `Requesting participant must have role "${r}"`,
		purpose: (r) => `Declared purpose must be "${r}"`,
	};
	return map[short]?.(right) ?? `${short} = ${right}`;
}

function rulesFor(rules: OdrlRule | OdrlRule[] | undefined): OdrlRule[] {
	if (!rules) return [];
	return Array.isArray(rules) ? rules : [rules];
}

export function summarisePolicy(policy: Record<string, unknown> | null | undefined): PolicySummary {
	if (!policy) return { permitted: [], prohibited: [], obligations: [], constraints: [] };

	const perms = rulesFor(policy['odrl:permission'] as OdrlRule | OdrlRule[] | undefined);
	const prohbs = rulesFor(policy['odrl:prohibition'] as OdrlRule | OdrlRule[] | undefined);
	const obligs = rulesFor(policy['odrl:obligation'] as OdrlRule | OdrlRule[] | undefined);

	const permitted = perms.map((r) => actionLabel(r['odrl:action']));
	const prohibited = prohbs.map((r) => actionLabel(r['odrl:action']));
	const obligations = obligs.map((r) => actionLabel(r['odrl:action']));

	const allConstraints = [...perms, ...prohbs, ...obligs].flatMap((r) => {
		const c = r['odrl:constraint'];
		if (!c) return [];
		return (Array.isArray(c) ? c : [c]).map(constraintSentence);
	});
	const constraints = [...new Set(allConstraints)];

	return { permitted, prohibited, obligations, constraints };
}
