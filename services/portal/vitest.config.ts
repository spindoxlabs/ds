import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

// Unit tests only. The Playwright journeys under `tests/ui/` are driven by the
// Playwright runner (`npm run test:ui`) and MUST be excluded here, or Vitest
// tries to execute them as plain modules and they fail on the missing stack.
export default defineConfig({
	resolve: {
		alias: {
			// SvelteKit's `$lib` maps to `src/lib`; Kit provides it in the build.
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
			// SvelteKit virtual modules do not exist outside the Kit build; stub the
			// ones our server modules import so they resolve under plain Vitest.
			'$env/dynamic/private': fileURLToPath(
				new URL('./tests/unit/stubs/env-dynamic-private.ts', import.meta.url),
			),
			'$env/dynamic/public': fileURLToPath(
				new URL('./tests/unit/stubs/env-dynamic-public.ts', import.meta.url),
			),
		},
	},
	test: {
		environment: 'node',
		include: ['tests/unit/**/*.{test,spec}.ts'],
		exclude: ['tests/ui/**', 'tests/unit/stubs/**', 'node_modules/**'],
	},
});
