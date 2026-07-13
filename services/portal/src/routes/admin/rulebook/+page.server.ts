import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

interface RulebookSection {
	title: string;
	body: string;
	bullets: string[];
}

function docsPath(): string {
	return env.DOCS_PATH ?? '/docs';
}

function fallbackDocsPath(): string {
	return resolve(process.cwd(), '../../docs');
}

function readRulebook(): string {
	for (const base of [docsPath(), fallbackDocsPath()]) {
		const path = resolve(base, 'rulebook.md');
		if (!existsSync(path)) continue;
		return readFileSync(path, 'utf-8');
	}
	return '';
}

function parseSections(markdown: string): RulebookSection[] {
	const sections: RulebookSection[] = [];
	const chunks = markdown.split(/\n## /g);
	for (const chunk of chunks.slice(1)) {
		const lines = chunk.trim().split('\n');
		const title = lines.shift()?.replace(/^##\s*/, '').trim() ?? 'Section';
		const bodyLines: string[] = [];
		const bullets: string[] = [];
		for (const line of lines) {
			const trimmed = line.trim();
			if (trimmed.startsWith('- ')) bullets.push(trimmed.slice(2));
			else if (trimmed && !trimmed.startsWith('|') && !trimmed.startsWith('---')) bodyLines.push(trimmed);
		}
		sections.push({ title, body: bodyLines.join(' '), bullets });
	}
	return sections;
}

export const load: PageServerLoad = async () => {
	const markdown = readRulebook();
	return {
		markdown,
		sections: parseSections(markdown),
		available: Boolean(markdown),
	};
};
