import { text } from '@sveltejs/kit';

const startedAt = Date.now();

export function GET() {
	const uptimeSeconds = (Date.now() - startedAt) / 1000;
	const body = [
		'# HELP ds_service_up Service liveness gauge.',
		'# TYPE ds_service_up gauge',
		'ds_service_up{service="ds-portal"} 1',
		'# HELP ds_service_uptime_seconds Service uptime in seconds.',
		'# TYPE ds_service_uptime_seconds gauge',
		`ds_service_uptime_seconds{service="ds-portal"} ${uptimeSeconds.toFixed(3)}`
	].join('\n');

	return text(`${body}\n`, {
		headers: {
			'content-type': 'text/plain; version=0.0.4'
		}
	});
}
