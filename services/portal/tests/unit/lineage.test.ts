import { describe, it, expect } from 'vitest';
import { classifyLineageGraph } from '../../src/lib/server/provenance';

// A graph shaped exactly as `provenance/services/jsonld_service.py` emits it:
// nodes carry @type prov:Entity/Activity/Agent; edges carry ds:source / ds:target
// for direction and prov:entity / prov:activity / prov:agent for what each end is.
const GRAPH = [
	{ '@id': 'urn:dataset:meters', '@type': 'prov:Entity', 'prov:label': 'Meters' },
	{ '@id': 'urn:activity:ingest', '@type': 'prov:Activity', 'prov:label': 'Ingest' },
	{ '@id': 'did:web:provider.test', '@type': 'prov:Agent', 'prov:label': 'Provider' },
	{
		'@id': 'urn:relation:1',
		'@type': 'prov:wasGeneratedBy',
		'ds:source': 'urn:dataset:meters',
		'ds:target': 'urn:activity:ingest',
		'prov:entity': 'urn:dataset:meters',
		'prov:activity': 'urn:activity:ingest',
	},
	{
		'@id': 'urn:relation:2',
		'@type': 'prov:wasAssociatedWith',
		'ds:source': 'urn:activity:ingest',
		'ds:target': 'did:web:provider.test',
		'prov:activity': 'urn:activity:ingest',
		'prov:agent': 'did:web:provider.test',
	},
];

describe('classifyLineageGraph', () => {
	it('reads edges from ds:source / ds:target', () => {
		const { nodes, edges } = classifyLineageGraph(GRAPH);
		expect(nodes).toHaveLength(3);
		expect(edges).toHaveLength(2);
		expect(edges[0]).toMatchObject({
			source: 'urn:dataset:meters',
			target: 'urn:activity:ingest',
			label: 'wasGeneratedBy',
		});
	});

	it('keeps an Activity→Agent edge, which carries no prov:entity at all', () => {
		// The defect this replaces: classifying on prov:entity + prov:activity
		// dropped every edge whose ends are not exactly {Entity, Activity} —
		// wasAssociatedWith, wasAttributedTo, actedOnBehalfOf, wasDerivedFrom.
		// Those are most of the graph.
		const { edges } = classifyLineageGraph(GRAPH);
		expect(edges.map((e) => e.label)).toContain('wasAssociatedWith');
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
