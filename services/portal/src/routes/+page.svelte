<script lang="ts">
  import MedallionBadge from '$lib/components/MedallionBadge.svelte';

  let { data } = $props();

  let search = $state('');
  const datasets = $derived(
    (data.datasets as Array<Record<string, unknown>>).filter((d) => {
      if (!search) return true;
      const title = String(d['dct:title'] ?? d['title'] ?? d['name'] ?? '').toLowerCase();
      const desc = String(d['dct:description'] ?? d['description'] ?? '').toLowerCase();
      return title.includes(search.toLowerCase()) || desc.includes(search.toLowerCase());
    }),
  );

  function getTitle(d: Record<string, unknown>): string {
    return String(d['dct:title'] ?? d['title'] ?? d['name'] ?? d['@id'] ?? 'Unnamed Dataset');
  }
  function getDesc(d: Record<string, unknown>): string {
    return String(d['dct:description'] ?? d['description'] ?? '');
  }
  function getId(d: Record<string, unknown>): string {
    return String(d['dct:identifier'] ?? d['@id'] ?? d['id'] ?? d['asset_id'] ?? '');
  }
  function getMedallion(d: Record<string, unknown>): string {
    const tags: unknown[] = Array.isArray(d['dcat:keyword']) ? (d['dcat:keyword'] as unknown[]) : [];
    return tags.find((t) => ['bronze', 'silver', 'gold'].includes(String(t))) as string ?? '';
  }
  function getAccessLevel(d: Record<string, unknown>): string {
    return String(d['access_level'] ?? d['accessRights'] ?? '');
  }
</script>

<svelte:head>
  <title>Dataspace Catalog</title>
</svelte:head>

<div class="space-y-6">
  <!-- Hero -->
  <div class="bg-gradient-to-br from-brand-700 to-brand-900 text-white rounded-2xl p-6 sm:p-8">
    <h1 class="text-2xl sm:text-3xl font-bold mb-2">Discover Datasets</h1>
    <p class="text-brand-200 mb-5">Browse open and contract-gated data offerings from the energy dataspace.</p>
    <div class="flex gap-2 max-w-lg">
      <input
        bind:value={search}
        type="search"
        placeholder="Search datasets…"
        class="flex-1 px-4 py-2 rounded-lg bg-white/10 border border-white/20 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-white/40 text-sm"
      />
    </div>
  </div>

  <!-- Error state -->
  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">
      Could not load catalogue: {data.error}
    </div>
  {/if}

  <!-- Results grid -->
  {#if datasets.length === 0 && !data.error}
    <p class="text-gray-500 text-center py-12">
      {search ? 'No datasets match your search.' : 'No datasets available.'}
    </p>
  {:else}
    <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {#each datasets as dataset}
        {@const id = getId(dataset)}
        {@const title = getTitle(dataset)}
        {@const desc = getDesc(dataset)}
        {@const medallion = getMedallion(dataset)}
        {@const access = getAccessLevel(dataset)}
        <div class="ds-card flex flex-col gap-3 hover:shadow-md transition-shadow">
          <div class="flex items-start justify-between gap-2">
            <h2 class="font-semibold text-gray-900 leading-snug">{title}</h2>
            <MedallionBadge tier={medallion} />
          </div>

          {#if desc}
            <p class="text-sm text-gray-600 line-clamp-2">{desc}</p>
          {/if}

          <div class="flex items-center gap-2 mt-auto">
            {#if access}
              <span class="ds-badge bg-blue-50 text-blue-700">{access}</span>
            {/if}
          </div>

          <a
            href="/consumer/catalog/{encodeURIComponent(id)}"
            class="ds-btn-primary text-center text-sm mt-1"
          >
            View offer →
          </a>
        </div>
      {/each}
    </div>
  {/if}
</div>
