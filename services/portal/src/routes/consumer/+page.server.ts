import { fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { subjectCredentialHeaders } from '$lib/server/connector';
import { getConsumerSubjectId } from '$lib/server/auth';

export const load: PageServerLoad = async ({ locals, fetch }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const subjectId = session ? getConsumerSubjectId(session) : '';
	const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';

	const headers = {
		...subjectCredentialHeaders(subjectId, session?.userVcJws),
		...(token ? { Authorization: `Bearer ${token}` } : {}),
	};

	try {
		const [requestsRes, transfersRes] = await Promise.all([
			fetch(`${connectorUrl}/consumer/requests`, { headers }),
			fetch(`${connectorUrl}/consumer/transfers`, { headers }),
		]);
		if (!requestsRes.ok) throw new Error(`requests ${requestsRes.status}`);
		if (!transfersRes.ok) throw new Error(`transfers ${transfersRes.status}`);
		const requests = await requestsRes.json();
		const transfers = await transfersRes.json();
		return {
			requests: Array.isArray(requests) ? requests : [],
			transfers: Array.isArray(transfers) ? transfers : [],
			error: null,
			revokeError: null,
		};
	} catch (e) {
		return {
			requests: [],
			transfers: [],
			error: e instanceof Error ? e.message : 'Failed',
			revokeError: null,
		};
	}
};

export const actions: Actions = {
	revoke: async ({ request, locals, fetch }) => {
		const session = await locals.auth();
		const token = session?.accessToken ?? '';
		const subjectId = session ? getConsumerSubjectId(session) : '';
		const connectorUrl = env.CONNECTOR_URL ?? 'http://ds-connector:30001';
		const form = await request.formData();
		const requestId = String(form.get('request_id') ?? '');
		if (!requestId) {
			return fail(400, { revokeError: 'Missing request id' });
		}

		const res = await fetch(`${connectorUrl}/consumer/requests/${encodeURIComponent(requestId)}/revoke`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...subjectCredentialHeaders(subjectId, session?.userVcJws),
				...(token ? { Authorization: `Bearer ${token}` } : {}),
			},
			body: JSON.stringify({ reason: 'Revoked by consumer user' }),
		});

		if (!res.ok) {
			const text = await res.text().catch(() => res.statusText);
			return fail(res.status, { revokeError: text || `Revoke failed with ${res.status}` });
		}
		return { revoked: true };
	},
};
