<script lang="ts">
  import type { AuditEntry } from '$lib/server/provenance';
  let { data } = $props();

  function exportCsv() {
    const rows = (data.events as AuditEntry[]).map((e) =>
      [e.occurred_at, e.event_type, e.agreement_id ?? '', e.provider_did ?? '', e.consumer_did ?? ''].join(','),
    );
    const csv = ['occurred_at,event_type,agreement_id,provider,consumer', ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audit-log.csv';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<svelte:head><title>Audit Log</title></svelte:head>

<div class="space-y-5">
  <div class="flex items-center justify-between">
    <h1 class="text-xl font-bold text-gray-900">Audit Log</h1>
    <button class="ds-btn-secondary text-sm" onclick={exportCsv}>Export CSV</button>
  </div>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {:else if (data.events as AuditEntry[]).length === 0}
    <p class="text-gray-500 py-8 text-center">No audit events found.</p>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left border-b border-gray-200 text-gray-500 text-xs uppercase">
            <th class="pb-2 pr-4">Timestamp</th>
            <th class="pb-2 pr-4">Event</th>
            <th class="pb-2 pr-4">Agreement</th>
            <th class="pb-2 pr-4">Provider</th>
            <th class="pb-2">Consumer</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {#each data.events as e}
            <tr>
              <td class="py-2 pr-4 text-gray-500 text-xs whitespace-nowrap">
                {new Date(e.occurred_at).toLocaleString()}
              </td>
              <td class="py-2 pr-4">
                <span class="ds-badge bg-blue-50 text-blue-700">{e.event_type}</span>
              </td>
              <td class="py-2 pr-4 font-mono text-xs text-gray-600">
                {e.agreement_id ? `${e.agreement_id.slice(0, 10)}…` : '—'}
              </td>
              <td class="py-2 pr-4 text-xs text-gray-600">{e.provider_did ?? '—'}</td>
              <td class="py-2 text-xs text-gray-600">{e.consumer_did ?? '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
