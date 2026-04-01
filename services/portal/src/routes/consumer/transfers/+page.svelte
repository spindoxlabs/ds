<script lang="ts">
  let { data } = $props();
  let queryResult = $state<string | null>(null);
  let queryError = $state<string | null>(null);
  let running = $state(false);

  async function runQuery(transferId: string, edrEndpoint: string, edrToken: string) {
    running = true;
    queryResult = null;
    queryError = null;
    try {
      const res = await fetch(edrEndpoint, {
        headers: { Authorization: edrToken },
      });
      queryResult = JSON.stringify(await res.json(), null, 2);
    } catch (e) {
      queryError = e instanceof Error ? e.message : 'Query failed';
    } finally {
      running = false;
    }
  }
</script>

<svelte:head><title>Transfers</title></svelte:head>

<div class="space-y-5">
  <h1 class="text-xl font-bold text-gray-900">Active Transfers</h1>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {:else if (data.transfers as unknown[]).length === 0}
    <p class="text-gray-500 py-8 text-center">No active transfers. Request access from the <a href="/consumer/catalog" class="text-brand-600 hover:underline">catalog</a>.</p>
  {:else}
    <div class="space-y-4">
      {#each data.transfers as t}
        {@const transfer = t as Record<string, unknown>}
        <div class="ds-card space-y-3">
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="font-mono text-sm text-gray-700">{String(transfer['transfer_id'] ?? transfer['id'] ?? '—')}</p>
              <p class="text-sm text-gray-500 mt-0.5">Asset: {String(transfer['asset_id'] ?? '—')}</p>
            </div>
            <span class="ds-badge bg-green-100 text-green-700">{String(transfer['state'] ?? 'STARTED')}</span>
          </div>

          {#if transfer['edr']}
            {@const edr = transfer['edr'] as Record<string, string>}
            <div class="border-t border-gray-100 pt-3">
              <p class="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">Endpoint Data Reference</p>
              <p class="font-mono text-xs text-gray-700 break-all">{edr['endpoint']}</p>
              <button
                class="ds-btn-primary text-sm mt-2"
                disabled={running}
                onclick={() => runQuery(String(transfer['transfer_id']), edr['endpoint'], edr['authorization'])}
              >
                {running ? 'Querying…' : 'Run query'}
              </button>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  {#if queryResult}
    <div class="ds-card">
      <p class="text-sm font-medium text-gray-700 mb-2">Query result</p>
      <pre class="text-xs bg-gray-900 text-green-300 rounded-lg p-3 overflow-x-auto max-h-64">{queryResult}</pre>
    </div>
  {/if}
  {#if queryError}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{queryError}</div>
  {/if}
</div>
