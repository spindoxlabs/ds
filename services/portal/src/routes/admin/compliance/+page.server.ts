import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

interface ComplianceFinding {
	check: string;
	message: string;
	dataset?: string;
}

interface ComplianceReport {
	profile: string;
	passed: boolean;
	generated_at?: string;
	datasets_checked?: number;
	checks?: string[];
	errors?: ComplianceFinding[];
	warnings?: ComplianceFinding[];
	artifacts?: Record<string, string>;
}

interface E2EStep {
	name: string;
	status: string;
	detail?: string;
	data?: Record<string, unknown>;
}

interface E2EReport {
	profile: string;
	status: string;
	generated_at?: string;
	steps?: E2EStep[];
	artifacts?: Record<string, string>;
}

function reportsPath(): string {
	return env.COMPLIANCE_REPORTS_PATH ?? '/reports';
}

function fallbackReportsPath(): string {
	return resolve(process.cwd(), '../../reports');
}

function readJson<T>(relativePath: string): T | null {
	for (const base of [reportsPath(), fallbackReportsPath()]) {
		const path = resolve(base, relativePath);
		if (!existsSync(path)) continue;
		try {
			return JSON.parse(readFileSync(path, 'utf-8')) as T;
		} catch {
			return null;
		}
	}
	return null;
}

function reportLink(relativePath: string): string {
	return relativePath;
}

export const load: PageServerLoad = async () => {
	const coreCompliance = readJson<ComplianceReport>('compliance/core-compliance-report.json');
	const coreE2E = readJson<E2EReport>('e2e/core-e2e-report.json');

	return {
		coreCompliance,
		coreE2E,
		evidence: {
			coreComplianceMd: reportLink('compliance/core-compliance-report.md'),
			coreDcat: reportLink('compliance/core-dcat-catalog.jsonld'),
			coreOdrl: reportLink('compliance/core-odrl-offers.jsonld'),
			coreE2EMd: reportLink('e2e/core-e2e-report.md'),
		},
		productionChecks: [
			'Docker secrets profile declared',
			'EDC Management API ports removed by production override',
			'HTTPS credential status registry required',
			'Production DID web identifiers required',
		],
	};
};
