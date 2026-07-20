import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

interface ServiceStatus {
	name: string;
	url: string;
	status: 'ok' | 'error' | 'unknown';
	detail?: string;
}

async function ping(name: string, url: string): Promise<ServiceStatus> {
	try {
		const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(3000) });
		const body = res.ok ? await res.json().catch(() => ({})) : {};
		return { name, url, status: res.ok ? 'ok' : 'error', detail: body.version ?? body.status };
	} catch (e) {
		return { name, url, status: 'error', detail: e instanceof Error ? e.message : 'unreachable' };
	}
}

export const load: PageServerLoad = async () => {
	const services = [
		{ name: 'ds-connector', url: env.CONNECTOR_URL ?? 'http://ds-connector:30001' },
		{ name: 'ds-provenance', url: env.PROVENANCE_URL ?? 'http://ds-provenance:30000' },
		{ name: 'dataset-api', url: env.CATALOGUE_URL ?? 'http://172.17.0.1:30002' },
	];

	const results = await Promise.all(services.map((s) => ping(s.name, s.url)));
	return { services: results };
};
