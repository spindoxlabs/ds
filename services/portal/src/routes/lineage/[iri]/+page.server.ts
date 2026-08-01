import type { PageServerLoad } from './$types';
import { getLineage, classifyLineageGraph } from '$lib/server/provenance';

export const load: PageServerLoad = async ({ params, url, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const iri = decodeURIComponent(params.iri);
	const direction = (url.searchParams.get('direction') ?? 'both') as string;
	const maxDepth = parseInt(url.searchParams.get('max_depth') ?? '5', 10);

	try {
		const lineage = await getLineage(iri, { direction, maxDepth }, token);
		const graph = (lineage['@graph'] ?? []) as Array<Record<string, unknown>>;
		const graphData = classifyLineageGraph(graph);

		return { iri, graphData, depth: lineage.depth, error: null };
	} catch (e) {
		return {
			iri,
			graphData: { nodes: [], edges: [] },
			depth: 0,
			error: e instanceof Error ? e.message : 'Failed to load lineage',
		};
	}
};
