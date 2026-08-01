/**
 * Dataset-policy resolution shared by the pages that summarise ODRL.
 *
 * Two JSON-LD shapes reach the portal: the dataset-api serves prefixed terms
 * (`dcat:distribution`, `odrl:hasPolicy`), and other sources serve them
 * unprefixed. Reading only one shape silently produced an empty policy, so both
 * the catalog detail page and the consent detail page must read through the same
 * lenient extractor.
 */
import { env } from '$env/dynamic/private';
import { summarisePolicy, type PolicySummary } from './odrl';

/** First present, non-empty value among the given key spellings. */
export function pick(obj: Record<string, unknown> | null | undefined, ...names: string[]): unknown {
	if (!obj) return undefined;
	for (const name of names) {
		const value = obj[name];
		if (value !== undefined && value !== null && value !== '') return value;
	}
	return undefined;
}

/**
 * The ODRL policy object for a dataset record — on the dataset itself or on its
 * first distribution, under the prefixed or unprefixed key. `null` when the
 * record carries none, which `summarisePolicy` renders as an empty summary.
 */
export function datasetPolicy(
	dataset: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
	if (!dataset) return null;
	const rawDistribution = pick(dataset, 'dcat:distribution', 'distribution');
	const distribution = Array.isArray(rawDistribution)
		? (rawDistribution as Array<Record<string, unknown>>)[0]
		: null;
	const rawPolicy =
		pick(dataset, 'odrl:hasPolicy', 'hasPolicy') ?? pick(distribution, 'odrl:hasPolicy', 'hasPolicy');
	const policy = Array.isArray(rawPolicy) ? rawPolicy[0] : rawPolicy;
	return policy && typeof policy === 'object' ? (policy as Record<string, unknown>) : null;
}

function catalogueUrl(): string {
	return env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
}

/**
 * Resolve one dataset from the local dataset-api catalogue by identifier.
 *
 * Consent is provider-side — the dataset is this participant's own — so the
 * local catalogue is the authority, not the federated index. Returns `null`
 * rather than throwing: a missing policy must degrade a page's summary, never
 * break the page.
 */
async function resolveDataset(
	datasetId: string,
	token: string,
	fetchFn: typeof fetch,
): Promise<Record<string, unknown> | null> {
	const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
	try {
		const listRes = await fetchFn(`${catalogueUrl()}/catalogue`, { headers });
		if (listRes.ok) {
			const raw = await listRes.json();
			const datasets: Array<Record<string, unknown>> = Array.isArray(raw)
				? raw
				: (raw?.datasets ?? raw?.['dcat:dataset'] ?? []);
			const match = datasets.find((item) => {
				const ids = [item['dct:identifier'], item['@id'], item['id'], item['asset_id']];
				return ids.map(String).includes(datasetId);
			});
			if (match) return match;
		}

		const res = await fetchFn(`${catalogueUrl()}/catalogue/${encodeURIComponent(datasetId)}`, { headers });
		if (!res.ok) return null;
		return (await res.json()) as Record<string, unknown>;
	} catch (e) {
		console.error('[ds-portal] dataset policy lookup failed:', e instanceof Error ? e.message : e);
		return null;
	}
}

/** The policy summary for a dataset, or an empty summary if it cannot be resolved. */
export async function datasetPolicySummary(
	datasetId: string,
	token: string,
	fetchFn: typeof fetch,
): Promise<PolicySummary> {
	const dataset = await resolveDataset(datasetId, token, fetchFn);
	return summarisePolicy(datasetPolicy(dataset));
}
