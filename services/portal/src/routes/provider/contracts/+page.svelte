<script lang="ts">
  import type { ContractAgreement } from '$lib/server/connector';
  let { data } = $props();
</script>

<svelte:head><title>Provider Contracts</title></svelte:head>

<div class="space-y-5">
  <h1 class="text-xl font-bold text-gray-900">Contract Agreements</h1>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {:else if (data.contracts as ContractAgreement[]).length === 0}
    <p class="text-gray-500 py-8 text-center">No contracts yet.</p>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left border-b border-gray-200 text-gray-500 text-xs uppercase">
            <th class="pb-2 pr-4">Agreement ID</th>
            <th class="pb-2 pr-4">Asset</th>
            <th class="pb-2 pr-4">Consumer</th>
            <th class="pb-2 pr-4">Status</th>
            <th class="pb-2">Agreed at</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {#each data.contracts as c}
            <tr>
              <td class="py-2 pr-4 font-mono text-xs text-gray-600">{c.agreement_id.slice(0, 14)}…</td>
              <td class="py-2 pr-4 text-gray-900">{c.asset_id}</td>
              <td class="py-2 pr-4 text-gray-700">{c.consumer_id}</td>
              <td class="py-2 pr-4">
                <span class="ds-badge {c.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}">
                  {c.status}
                </span>
              </td>
              <td class="py-2 text-gray-500">
                {c.agreed_at ? new Date(c.agreed_at).toLocaleDateString() : '—'}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
