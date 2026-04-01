<script lang="ts">
  import MedallionBadge from '$lib/components/MedallionBadge.svelte';

  let { data } = $props();
  let search = $state('');

  const datasets = $derived(
    (data.datasets as Array<Record<string, unknown>>).filter((d) => {
      if (!search) return true;
      const t = String(d['dct:title'] ?? d['title'] ?? d['name'] ?? '').toLowerCase();
      return t.includes(search.toLowerCase());
    }),
  );

  function getTitle(d: Record<string, unknown>) {
    return String(d['dct:title'] ?? d['title'] ?? d['name'] ?? 'Unnamed');
  }
  function getId(d: Record<string, unknown>) {
    return String(d['@id'] ?? d['id'] ?? d['asset_id'] ?? '');
  }
  function getMedallion(d: Record<string, unknown>) {
    const tags = Array.isArray(d['dcat:keyword']) ? (d['dcat:keyword'] as string[]) : [];
    return tags.find((t) => ['bronze', 'silver', 'gold'].includes(t)) ?? '';
  }
  function getAccess(d: Record<string, unknown>) {
    return String(d['access_level'] ?? d['accessRights'] ?? '');
  }
</script>

<svelte:head><title>Catalog — Consumer</title></svelte:head>

<div class="space-y-5">
  <div class="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
    <h1 class="text-xl font-bold text-gray-900">Discover Datasets</h1>
    <input
      bind:value={search}
      type="search"
      placeholder="Search…"
      class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-600 focus:outline-none"
    />
  </div>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {:else if datasets.length === 0}
    <p class="text-gray-500 py-8 text-center">No datasets available.</p>
  {:else}
    <div class="grid sm:grid-cols-2 gap-4">
      {#each datasets as d}
        {@const id = getId(d)}
        {@const title = getTitle(d)}
        <div class="ds-card flex flex-col gap-2 hover:shadow-md transition-shadow">
          <div class="flex items-center gap-2 flex-wrap">
            <h2 class="font-semibold text-gray-900 flex-1">{title}</h2>
            <MedallionBadge tier={getMedallion(d)} />
          </div>
          {#if getAccess(d)}
            <span class="ds-badge bg-blue-50 text-blue-700 self-start">{getAccess(d)}</span>
          {/if}
          <a href="/consumer/catalog/{encodeURIComponent(id)}" class="ds-btn-primary text-sm mt-auto text-center">
            View offer →
          </a>
        </div>
      {/each}
    </div>
  {/if}
</div>
