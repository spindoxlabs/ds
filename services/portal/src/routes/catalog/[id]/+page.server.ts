import type { PageServerLoad } from './$types';
import { summarisePolicy } from '$lib/server/odrl';
import { env } from '$env/dynamic/private';
import { getConsumerSubjectId } from '$lib/server/auth';
import { subjectCredentialHeaders } from '$lib/server/connector';

export const load: PageServerLoad = async ({ params, locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session ? getConsumerSubjectId(session) : '';
	const assetId = decodeURIComponent(params.id);
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
	const catalogueUrl = env.CATALOGUE_URL ?? 'http://172.17.0.1:30002';
	const defaultCounterPartyAddress =
		env.CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS ?? 'http://edc-provider:19194/protocol/2025-1';
	const defaultAssigner =
		env.CONSUMER_DEFAULT_ASSIGNER ?? 'did:web:provider.dataspaces.test';

	const idOf = (value: unknown): string => {
		if (!value) return '';
		if (typeof value === 'string') return value;
		if (typeof value === 'object') {
			const obj = value as Record<string, unknown>;
			return String(obj['@id'] ?? obj.id ?? obj.identifier ?? '');
		}
		return String(value);
	};

	try {
		const listRes = await fetch(`${catalogueUrl}/catalogue`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!listRes.ok) throw new Error(`${listRes.status}`);
		const raw = await listRes.json();
		const datasets: Array<Record<string, unknown>> = Array.isArray(raw)
			? raw
			: (raw?.datasets ?? raw?.['dcat:dataset'] ?? []);
		let dataset = datasets.find((item) => {
			const ids = [item['dct:identifier'], item['@id'], item['id'], item['asset_id']];
			return ids.map(String).includes(assetId);
		});

		if (!dataset) {
			const res = await fetch(`${catalogueUrl}/catalogue/${encodeURIComponent(assetId)}`, {
				headers: token ? { Authorization: `Bearer ${token}` } : {},
			});
			if (!res.ok) throw new Error(`${res.status}`);
			dataset = await res.json() as Record<string, unknown>;
		}

		const distribution = Array.isArray(dataset['dcat:distribution'])
			? (dataset['dcat:distribution'] as Array<Record<string, unknown>>)[0]
			: null;
		const rawPolicy = dataset['odrl:hasPolicy'] ?? distribution?.['odrl:hasPolicy'];
		const policy = Array.isArray(rawPolicy) ? rawPolicy[0] : rawPolicy;
		const policySummary = summarisePolicy(policy as Record<string, unknown> ?? null);
		const policyObject = policy && typeof policy === 'object'
			? structuredClone(policy as Record<string, unknown>)
			: null;
		const offerId = `${assetId}#offer`;
		const assigner =
			idOf(policyObject?.['odrl:assigner'])
			|| idOf(dataset['edc:assigner'])
			|| idOf(dataset['provider_participant_id'])
			|| defaultAssigner;
		const counterPartyAddress =
			idOf(dataset['edc:counterPartyAddress'])
			|| idOf(dataset['counter_party_address'])
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
					...subjectCredentialHeaders(subjectId, session?.userVcJws),
					...(token ? { Authorization: `Bearer ${token}` } : {}),
				},
			});
			if (requestsRes.ok) {
				const requests = await requestsRes.json();
				existingRequest = Array.isArray(requests)
					? (
						requests.find((item) => {
							const status = String(item?.status ?? '').trim().toLowerCase();
							return (
								String(item?.asset_id ?? item?.assetId ?? '') === assetId
								&& ['negotiating', 'finalized', 'transferring', 'transferred'].includes(status)
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
