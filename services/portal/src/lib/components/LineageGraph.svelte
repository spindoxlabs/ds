<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let {
    graphData,
  }: {
    graphData: {
      nodes: Array<{ id: string; label: string; type: string }>;
      edges: Array<{ id: string; source: string; target: string; label: string }>;
    };
  } = $props();

  let container: HTMLDivElement;
  let cy: unknown = null;
  let selectedNode = $state<{ id: string; label: string; type: string } | null>(null);

  const nodeColors: Record<string, string> = {
    Entity: '#3b82f6',
    Activity: '#22c55e',
    Agent: '#f97316',
  };

  onMount(async () => {
    const [cytoscapeLib, dagre, cytoscapeDagre] = await Promise.all([
      import('cytoscape'),
      import('dagre'),
      import('cytoscape-dagre'),
    ]);
    const cytoscape = cytoscapeLib.default;
    cytoscapeDagre.default(cytoscape, dagre.default);
    const createGraph = cytoscape as unknown as (options: Record<string, unknown>) => unknown;

    cy = createGraph({
      container,
      elements: [
        ...graphData.nodes.map((n) => ({
          data: { id: n.id, label: n.label || n.id.split('/').pop() || n.id, type: n.type },
        })),
        ...graphData.edges.map((e) => ({
          data: { id: e.id, source: e.source, target: e.target, label: e.label },
        })),
      ],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': (ele: { data: (k: string) => string }) =>
              nodeColors[ele.data('type')] ?? '#94a3b8',
            label: 'data(label)',
            'font-size': '11px',
            color: '#1e293b',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 40,
            height: 40,
          },
        },
        {
          selector: 'edge',
          style: {
            'line-color': '#94a3b8',
            'target-arrow-color': '#94a3b8',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': '9px',
            color: '#64748b',
            'text-rotation': 'autorotate',
          },
        },
        {
          selector: ':selected',
          style: { 'border-width': 3, 'border-color': '#2563eb' },
        },
      ],
      layout: { name: 'dagre', rankDir: 'LR', padding: 24 },
    });

    (cy as { on: (event: string, selector: string, cb: (evt: { target: { data: (k: string) => string } }) => void) => void }).on('tap', 'node', (evt) => {
      const d = evt.target.data;
      selectedNode = { id: d('id'), label: d('label'), type: d('type') };
    });
  });

  onDestroy(() => {
    if (cy) (cy as { destroy: () => void }).destroy();
  });

  function exportSvg() {
    if (!cy) return;
    const svg = (cy as { svg: (opts: Record<string, unknown>) => string }).svg({ scale: 2, full: true });
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'lineage.svg';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="flex gap-4 h-full">
  <!-- Graph canvas -->
  <div bind:this={container} class="flex-1 min-h-96 rounded-xl border border-gray-200 bg-white"></div>

  <!-- Side panel -->
  {#if selectedNode}
    <div class="w-64 ds-card text-sm shrink-0">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-medium text-gray-900">Node detail</h3>
        <button onclick={() => (selectedNode = null)} class="text-gray-400 hover:text-gray-600">&times;</button>
      </div>
      <dl class="space-y-2">
        <div>
          <dt class="text-xs text-gray-500 uppercase tracking-wide">Type</dt>
          <dd class="mt-0.5 font-medium" style="color: {nodeColors[selectedNode.type] ?? '#64748b'}">{selectedNode.type}</dd>
        </div>
        <div>
          <dt class="text-xs text-gray-500 uppercase tracking-wide">Label</dt>
          <dd class="mt-0.5 text-gray-700">{selectedNode.label}</dd>
        </div>
        <div>
          <dt class="text-xs text-gray-500 uppercase tracking-wide">IRI</dt>
          <dd class="mt-0.5 font-mono text-xs text-gray-600 break-all">{selectedNode.id}</dd>
        </div>
      </dl>
    </div>
  {/if}
</div>

<!-- Legend + export -->
<div class="flex items-center gap-4 mt-3 text-xs text-gray-600">
  {#each Object.entries(nodeColors) as [type, color]}
    <span class="flex items-center gap-1.5">
      <span class="w-3 h-3 rounded-full inline-block" style="background:{color}"></span>
      {type}
    </span>
  {/each}
  <button onclick={exportSvg} class="ml-auto ds-btn-secondary text-xs py-1 px-2">Export SVG</button>
</div>
