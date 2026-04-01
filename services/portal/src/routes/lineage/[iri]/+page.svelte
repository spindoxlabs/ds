<script lang="ts">
  import { browser } from '$app/environment';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';

  let { data } = $props();

  let direction = $state($page.url.searchParams.get('direction') ?? 'both');
  let maxDepth = $state(parseInt($page.url.searchParams.get('max_depth') ?? '5', 10));

  function applyFilters() {
    const url = new URL($page.url);
    url.searchParams.set('direction', direction);
    url.searchParams.set('max_depth', String(maxDepth));
    goto(url.toString(), { replaceState: true, invalidateAll: true });
  }

  // Lazy-load LineageGraph (cytoscape) only in browser
  let LineageGraph: typeof import('$lib/components/LineageGraph.svelte').default | null = $state(null);
  if (browser) {
    import('$lib/components/LineageGraph.svelte').then((m) => (LineageGraph = m.default));
  }

  const shortIri = $derived(data.iri.split('/').pop() ?? data.iri);
</script>

<svelte:head>
  <title>Lineage: {shortIri}</title>
</svelte:head>

<div class="space-y-4">
  <div class="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
    <div>
      <h1 class="text-xl font-bold text-gray-900">Lineage</h1>
      <p class="text-sm font-mono text-gray-500 break-all">{data.iri}</p>
    </div>
    <div class="flex items-center gap-2 flex-wrap text-sm">
      <select
        bind:value={direction}
        class="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-600 focus:outline-none"
      >
        <option value="both">Both directions</option>
        <option value="upstream">Upstream</option>
        <option value="downstream">Downstream</option>
      </select>
      <select
        bind:value={maxDepth}
        class="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:ring-2 focus:ring-brand-600 focus:outline-none"
      >
        {#each [2, 3, 5, 10] as d}
          <option value={d}>Depth {d}</option>
        {/each}
      </select>
      <button class="ds-btn-secondary text-sm" onclick={applyFilters}>Apply</button>
    </div>
  </div>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {:else if data.graphData.nodes.length === 0}
    <p class="text-gray-500 py-8 text-center">No lineage data found for this IRI.</p>
  {:else if LineageGraph}
    <div class="h-[520px]">
      <LineageGraph graphData={data.graphData} />
    </div>
  {:else}
    <div class="h-32 flex items-center justify-center text-gray-400 text-sm">Loading graph…</div>
  {/if}
</div>
