/**
 * A backend answered with a non-2xx status.
 *
 * The message is the same `"<status> <url>: <body>"` text the fetch wrappers
 * always threw, so anything that only reads `message` is unchanged. What this
 * adds is the status and body as fields, so a page can tell a refusal from an
 * outage without parsing its own error string.
 */
export class ServiceError extends Error {
	constructor(
		readonly status: number,
		readonly url: string,
		readonly body: string,
	) {
		super(`${status} ${url}: ${body}`);
		this.name = 'ServiceError';
	}

	/** FastAPI's `{"detail": "..."}`, when the body is that; otherwise null. */
	get detail(): string | null {
		try {
			const parsed = JSON.parse(this.body);
			return typeof parsed?.detail === 'string' ? parsed.detail : null;
		} catch {
			return null;
		}
	}
}
