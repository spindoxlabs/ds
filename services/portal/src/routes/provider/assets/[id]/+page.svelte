<script lang="ts">
  let { data } = $props();
  let activeTab = $state<'contracts' | 'consents'>('contracts');
</script>

<svelte:head>
  <title>{data.assetId} — Provider</title>
</svelte:head>

<div class="space-y-5">
  <div class="flex items-center gap-3">
    <a href="/provider/assets" class="text-sm text-brand-600 hover:underline">← Assets</a>
    <h1 class="text-xl font-bold text-gray-900 font-mono">{data.assetId}</h1>
  </div>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {/if}

  <!-- Tabs -->
  <div class="flex gap-1 border-b border-gray-200">
    {#each [{ key: 'contracts', label: 'Contracts' }, { key: 'consents', label: 'Consents' }] as tab}
      <button
        onclick={() => (activeTab = tab.key as typeof activeTab)}
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px
               {activeTab === tab.key
                 ? 'border-brand-600 text-brand-700'
                 : 'border-transparent text-gray-500 hover:text-gray-700'}"
      >
        {tab.label}
      </button>
    {/each}
  </div>

  {#if activeTab === 'contracts'}
    {#if data.contracts.length === 0}
      <p class="text-gray-500 text-sm py-4">No contracts for this asset.</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left border-b border-gray-200 text-gray-500 text-xs uppercase">
              <th class="pb-2 pr-4">Agreement ID</th>
              <th class="pb-2 pr-4">Consumer</th>
              <th class="pb-2 pr-4">Status</th>
              <th class="pb-2">Agreed at</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            {#each data.contracts as c}
              <tr class="py-2">
                <td class="py-2 pr-4 font-mono text-xs text-gray-700">{c.agreement_id.slice(0, 12)}…</td>
                <td class="py-2 pr-4 text-gray-900">{c.consumer_id}</td>
                <td class="py-2 pr-4">
                  <span class="ds-badge {c.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}">
                    {c.status}
                  </span>
                </td>
                <td class="py-2 text-gray-500">{c.agreed_at ? new Date(c.agreed_at).toLocaleDateString() : '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else if activeTab === 'consents'}
    <p class="text-sm text-gray-500">
      Consent details are managed per data subject. For privacy, only aggregate counts are shown here.
    </p>
    <div class="ds-card text-center py-6">
      <p class="text-3xl font-bold text-gray-900">{data.contracts.length}</p>
      <p class="text-sm text-gray-500 mt-1">Active contracts with consent requirement</p>
    </div>
  {/if}
</div>
