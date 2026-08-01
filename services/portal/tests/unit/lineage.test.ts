import { describe, it, expect } from 'vitest';
import { classifyLineageGraph } from '../../src/lib/server/provenance';

// A graph shaped exactly as `provenance/services/jsonld_service.py` emits it:
// nodes carry @type prov:Entity/Activity, edges carry prov:entity / prov:activity.
const GRAPH = [
	{ '@id': 'urn:dataset:meters', '@type': 'prov:Entity', 'prov:label': 'Meters' },
	{ '@id': 'urn:activity:ingest', '@type': 'prov:Activity', 'prov:label': 'Ingest' },
	{
		'@id': 'urn:relation:1',
		'@type': 'prov:wasGeneratedBy',
		'prov:entity': 'urn:dataset:meters',
		'prov:activity': 'urn:activity:ingest',
	},
];

describe('classifyLineageGraph', () => {
	it('reads edges from prov:entity / prov:activity, not subject / object', () => {
		const { nodes, edges } = classifyLineageGraph(GRAPH);
		expect(nodes).toHaveLength(2);
		// The defect: with the old subject/object keys this was 0.
		expect(edges).toHaveLength(1);
		expect(edges[0]).toMatchObject({
			source: 'urn:dataset:meters',
			target: 'urn:activity:ingest',
			label: 'wasGeneratedBy',
		});
	});

	it('does not misread a node as an edge', () => {
		const { edges } = classifyLineageGraph([{ '@id': 'urn:x', '@type': 'prov:Agent', 'prov:label': 'Op' }]);
		expect(edges).toHaveLength(0);
	});

	it('takes the first element of an array @type (energy overlay) for the node type', () => {
		const { nodes } = classifyLineageGraph([
			{ '@id': 'urn:d', '@type': ['prov:Entity', 'saref:Measurement'], 'prov:label': 'D' },
		]);
		expect(nodes[0].type).toBe('Entity');
	});
});
