import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// The port is `PORT` at runtime (the Dockerfile sets 30004); adapter-node
		// takes no port option.
		adapter: adapter(),
		// `R17`. SvelteKit hashes or nonces the inline scripts it renders itself
		// (`mode: 'auto'`), so `script-src` needs no `unsafe-inline`. Styles do:
		// Svelte writes `style=` attributes and Vite injects `<style>` in dev.
		// `form-action` is left unset on purpose — sign-in and sign-out post here
		// and are redirected to the SSO host, whose address is runtime config.
		// The other headers (nosniff, Referrer-Policy) are set in `hooks.server.ts`.
		csp: {
			mode: 'auto',
			directives: {
				'default-src': ['self'],
				'script-src': ['self'],
				'style-src': ['self', 'unsafe-inline'],
				'img-src': ['self', 'data:'],
				'font-src': ['self'],
				'connect-src': ['self'],
				'object-src': ['none'],
				'base-uri': ['self'],
				'frame-ancestors': ['none'],
			},
		},
	},
};

export default config;
