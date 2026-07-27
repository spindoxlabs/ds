import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import ts from 'typescript-eslint';

/**
 * `npm run lint` was declared in package.json long before eslint was a
 * dependency, so it had never once run. This is the minimum that makes it real:
 * the recommended sets, plus the two rules that matter in a SvelteKit app where
 * server-only modules and browser code share a `src/` tree.
 */
export default ts.config(
	js.configs.recommended,
	...ts.configs.recommended,
	...svelte.configs['flat/recommended'],
	{
		languageOptions: {
			globals: { ...globals.browser, ...globals.node },
		},
		rules: {
			// SvelteKit's `$props()`/`$derived()` runes and `+page.server.ts` exports
			// are full of intentionally-unused destructuring; underscore opts out.
			'@typescript-eslint/no-unused-vars': [
				'error',
				{ argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
			],
			// Loader data crosses the SSR boundary as JSON, so `any` is sometimes
			// the honest type. Flag it, do not fail the build over it.
			'@typescript-eslint/no-explicit-any': 'warn',

			// The portal is served from the root of its own host and never sets
			// `base`, so `resolve()` would wrap ~30 plain hrefs to buy nothing. Turn
			// it back on the day this app is mounted under a path prefix.
			'svelte/no-navigation-without-resolve': 'off',

			// Real, and worth fixing: an unkeyed `{#each}` re-uses DOM nodes by
			// index, which reorders form state when a list changes underneath. Left
			// as a warning rather than silenced, because ~34 lists predate this
			// config and fixing them is its own change, not a lint-config decision.
			'svelte/require-each-key': 'warn',
		},
	},
	{
		files: ['**/*.svelte'],
		languageOptions: {
			parserOptions: { parser: ts.parser },
		},
	},
	{
		ignores: [
			'.svelte-kit/',
			'build/',
			'node_modules/',
			'test-results/',
			'playwright-report/',
		],
	},
);
