import type { PageServerLoad } from './$types';
import { summarisePolicy } from '$lib/server/odrl';
import { env } from '$env/dynamic/private';
import { getConsumerSubjectId, vcJwsForRole } from '$lib/server/auth';
import { subjectCredentialHeaders } from '$lib/server/connector';

export const load: PageServerLoad = async ({ params, locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session ? getConsumerSubjectId(session) : '';
	const assetId = decodeURIComponent(params.id);
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const federatedUrl = env.FEDERATED_CATALOG_URL;
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
	const defaultCounterPartyAddress =
		env.CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS ?? 'http://172.17.0.1:19194/protocol/2025-1';
	const defaultAssigner =
		env.CONSUMER_DEFAULT_ASSIGNER ?? 'did:web:rec.dataspaces.localhost';

	// Two JSON-LD shapes reach this page: the dataset-api serves prefixed terms
	// (`dcat:distribution`, `odrl:hasPolicy`), the federated catalog serves its
	// own @context with them unprefixed. Reading only the prefixed form left
	// federated datasets with no policy and an assigner falling back to the
	// deployment default — a negotiation against the wrong provider.
	const pick = (obj: Record<string, unknown> | null | undefined, ...names: string[]): unknown => {
		if (!obj) return undefined;
		for (const name of names) {
			const value = obj[name];
			if (value !== undefined && value !== null && value !== '') return value;
		}
		return undefined;
	};

	const idOf = (value: unknown): string => {
		if (!value) return '';
		if (typeof value === 'string') return value;
		if (typeof value === 'object') {
			const obj = value as Record<string, unknown>;
			return String(obj['@id'] ?? obj.id ?? obj.identifier ?? '');
		}
		return String(value);
	};

	const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

	// Resolve from the federated catalog first, as the landing page does. A
	// dataset discovered from another participant only exists there — resolving
	// detail from the local dataset-api alone would 404 it.
	const fromFederatedCatalog = async (): Promise<Record<string, unknown> | null> => {
		if (!federatedUrl) return null;
		try {
			const res = await fetch(`${federatedUrl}/catalog/${encodeURIComponent(assetId)}`, { headers });
			if (!res.ok) return null;
			return (await res.json()) as Record<string, unknown>;
		} catch (e) {
			console.error(
				'[ds-portal] Federated catalog detail unavailable, falling back to dataset-api:',
				e instanceof Error ? e.message : e,
			);
			return null;
		}
	};

	const fromDatasetApi = async (): Promise<Record<string, unknown>> => {
		const listRes = await fetch(`${catalogueUrl}/catalogue`, { headers });
		if (!listRes.ok) throw new Error(`${listRes.status}`);
		const raw = await listRes.json();
		const datasets: Array<Record<string, unknown>> = Array.isArray(raw)
			? raw
			: (raw?.datasets ?? raw?.['dcat:dataset'] ?? []);
		const match = datasets.find((item) => {
			const ids = [item['dct:identifier'], item['@id'], item['id'], item['asset_id']];
			return ids.map(String).includes(assetId);
		});
		if (match) return match;

		const res = await fetch(`${catalogueUrl}/catalogue/${encodeURIComponent(assetId)}`, { headers });
		if (!res.ok) throw new Error(`${res.status}`);
		return (await res.json()) as Record<string, unknown>;
	};

	try {
		const dataset = (await fromFederatedCatalog()) ?? (await fromDatasetApi());

		const rawDistribution = pick(dataset, 'dcat:distribution', 'distribution');
		const distribution = Array.isArray(rawDistribution)
			? (rawDistribution as Array<Record<string, unknown>>)[0]
			: null;
		const rawPolicy =
			pick(dataset, 'odrl:hasPolicy', 'hasPolicy')
			?? pick(distribution, 'odrl:hasPolicy', 'hasPolicy');
		const policy = Array.isArray(rawPolicy) ? rawPolicy[0] : rawPolicy;
		const policySummary = summarisePolicy(policy as Record<string, unknown> ?? null);
		const policyObject = policy && typeof policy === 'object'
			? structuredClone(policy as Record<string, unknown>)
			: null;
		const offerId = `${assetId}#offer`;
		const assigner =
			idOf(pick(policyObject, 'odrl:assigner', 'assigner'))
			|| idOf(pick(dataset, 'edc:assigner', 'assigner'))
			|| idOf(pick(dataset, 'provider_participant_id'))
			|| defaultAssigner;
		// A federated record carries the real DSP endpoint on its access service.
		// Preferring the default over it would negotiate against whichever
		// provider the deployment happens to name — wrong as soon as the catalog
		// federates more than one.
		const accessService = pick(distribution, 'dcat:accessService', 'accessService') as
			| Record<string, unknown>
			| undefined;
		const counterPartyAddress =
			idOf(pick(dataset, 'edc:counterPartyAddress', 'counter_party_address'))
			|| String(pick(accessService, 'endpointURL', 'dcat:endpointURL') ?? '')
			|| defaultCounterPartyAddress;

		if (policyObject) {
			policyObject['@id'] = offerId;
			policyObject['odrl:assigner'] = { '@id': assigner };
			policyObject['odrl:target'] = { '@id': assetId };
		}

		let existingRequest: Record<string, unknown> | null = null;
		try {
			const requestsRes = await fetch(`${connectorUrl}/consumer/requests`, {
				headers: {
					...subjectCredentialHeaders(subjectId, vcJwsForRole(session, 'ConsumerUser')),
					...(token ? { Authorization: `Bearer ${token}` } : {}),
				},
			});
			if (requestsRes.ok) {
				const requests = await requestsRes.json();
				existingRequest = Array.isArray(requests)
					? (
						requests.find((item) => {
							const status = String(item?.status ?? '').trim().toLowerCase();
							// Mirrors the connector's own live-request set
							// (api/v1/consumer.py:239). Omitting awaiting_consent here
							// would let a request parked on a consent decision look
							// absent, and offer a duplicate negotiation.
							return (
								String(item?.asset_id ?? item?.assetId ?? '') === assetId
								&& ['negotiating', 'awaiting_consent', 'finalized', 'transferring', 'transferred'].includes(status)
							);
						}) ?? null
					)
					: null;
			}
		} catch {
			existingRequest = null;
		}

		return {
			dataset,
			policySummary,
			assetId,
			existingRequest,
			negotiation: {
				counterPartyAddress,
				offerId,
				assigner,
				odrlPolicy: policyObject,
			},
			error: null,
		};
	} catch (e) {
		return { dataset: null, policySummary: null, assetId, negotiation: null, error: e instanceof Error ? e.message : 'Not found' };
	}
};
