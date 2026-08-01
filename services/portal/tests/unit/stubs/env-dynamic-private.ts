// Stub for SvelteKit's `$env/dynamic/private` virtual module under Vitest.
// The real module exposes runtime env; tests read process.env and set what they need.
export const env: Record<string, string | undefined> = process.env;
