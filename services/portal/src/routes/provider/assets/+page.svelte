<script lang="ts">
  import { enhance } from '$app/forms';
  import type { ProviderAsset } from '$lib/server/connector';
  import type { ServerRoles } from '$lib/server/auth';

  let { data, form } = $props();
  let syncing = $state(false);
  let search = $state('');

  const roles = $derived(data.roles as ServerRoles);
  const userOrgs = $derived(new Set(roles?.organizations ?? []));
  const canSync = $derived(roles?.isAdmin || userOrgs.size > 0);

  const assets = $derived(
    (data.assets as ProviderAsset[]).filter((a) => {
      return !search || a.asset_id.toLowerCase().includes(search.toLowerCase());
    }),
  );

  function canManageAsset(asset: ProviderAsset): boolean {
    if (roles?.isAdmin) return true;
    if (!asset.owner) return true;
    return userOrgs.has(asset.owner);
  }
</script>

<svelte:head>
  <title>Provider Assets</title>
</svelte:head>

<div class="space-y-5">
  <div class="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
    <div>
      <h1 class="text-xl font-bold text-gray-900">Provider Assets</h1>
      {#if userOrgs.size > 0 && !roles?.isAdmin}
        <p class="text-xs text-gray-500 mt-1">
          You can manage datasets owned by: {[...userOrgs].join(', ')}
        </p>
      {/if}
    </div>
    {#if canSync}
      <form
        method="POST"
        action="?/sync"
        use:enhance={() => {
          syncing = true;
          return async ({ update }) => {
            syncing = false;
            await update();
          };
        }}
      >
        <button type="submit" disabled={syncing} class="ds-btn-primary text-sm">
          {syncing ? 'Syncing…' : 'Sync governance'}
        </button>
      </form>
    {/if}
  </div>

  {#if form?.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{form.error}</div>
  {/if}
  {#if form?.synced !== undefined}
    <div class="ds-card border-green-200 bg-green-50 text-green-700 text-sm">
      Synced {form.synced} asset{form.synced !== 1 ? 's' : ''} to EDC.
    </div>
  {/if}
  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {/if}

  <!-- Filters -->
  <div class="flex flex-wrap gap-2">
    <input
      bind:value={search}
      type="search"
      placeholder="Search assets…"
      class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:ring-2 focus:ring-brand-600 focus:outline-none"
    />
  </div>

  <!-- Asset list -->
  {#if assets.length === 0}
    <p class="text-gray-500 py-8 text-center">No assets found.</p>
  {:else}
    <div class="space-y-3">
      {#each assets as asset}
        <div class="ds-card flex items-start gap-3" class:opacity-60={!canManageAsset(asset)}>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <h2 class="font-mono font-medium text-gray-900">{asset.asset_id}</h2>
              {#if asset.edc_synced}
                <span class="ds-badge bg-green-100 text-green-700">● active</span>
              {:else}
                <span class="ds-badge bg-gray-100 text-gray-500">○ not synced</span>
              {/if}
            </div>
            {#if asset.owner}
              <p class="text-sm text-gray-500 mt-1">
                Owned by <span class="font-medium text-gray-700">{asset.owner}</span>
                {#if asset.ownerDid}
                  <span class="text-xs text-gray-400 ml-1" title={asset.ownerDid}>({asset.ownerDid})</span>
                {/if}
              </p>
            {/if}
            {#if asset.description}
              <p class="text-sm text-gray-600 mt-1">{asset.description}</p>
            {/if}
            {#if asset.tags?.length}
              <div class="flex flex-wrap gap-1 mt-2">
                {#each asset.tags as tag}
                  <span class="ds-badge bg-gray-100 text-gray-600">{tag}</span>
                {/each}
              </div>
            {/if}
          </div>
          <a href="/provider/assets/{encodeURIComponent(asset.asset_id)}" class="ds-btn-secondary text-sm shrink-0">
            View →
          </a>
        </div>
      {/each}
    </div>
  {/if}
</div>
