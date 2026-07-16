import type { PageServerLoad } from './$types';
import { getLineage, type ProvNode, type LineageEdge } from '$lib/server/provenance';

export const load: PageServerLoad = async ({ params, url, locals }) => {
	const session = await locals.auth();
	const token = session?.accessToken ?? '';
	const iri = decodeURIComponent(params.iri);
	const direction = (url.searchParams.get('direction') ?? 'both') as string;
	const maxDepth = parseInt(url.searchParams.get('max_depth') ?? '5', 10);

	try {
		const lineage = await getLineage(iri, { direction, maxDepth }, token);
		const graph = lineage['@graph'] ?? [];

		// Split nodes and edges
		const nodes: { id: string; label: string; type: string }[] = [];
		const edges: { id: string; source: string; target: string; label: string }[] = [];

		for (const item of graph) {
			const i = item as Record<string, unknown>;
			if (i['subject'] && i['object']) {
				// It's an edge
				const edge = i as unknown as LineageEdge;
				edges.push({
					id: edge['@id'],
					source: edge['subject'],
					target: edge['object'],
					label: String(edge['@type']).split(':').pop() ?? '',
				});
			} else {
				// It's a node
				const node = i as unknown as ProvNode;
				nodes.push({
					id: node['@id'],
					label: String(node['prov:label'] ?? node['@id'].split('/').pop() ?? node['@id']),
					type: String(node['@type']).split(':').pop() ?? 'Entity',
				});
			}
		}

		return { iri, graphData: { nodes, edges }, depth: lineage.depth, error: null };
	} catch (e) {
		return {
			iri,
			graphData: { nodes: [], edges: [] },
			depth: 0,
			error: e instanceof Error ? e.message : 'Failed to load lineage',
		};
	}
};
