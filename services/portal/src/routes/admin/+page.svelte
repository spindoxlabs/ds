<script lang="ts">
  import type { AuditEntry } from '$lib/server/provenance';

  let { data } = $props();

  // null means "could not be read", which is not the same as zero — a zero is a
  // fact about the dataspace, an unreadable count is a fact about the instance.
  function show(value: number | null): string {
    return value === null ? '—' : String(value);
  }

  const sections = [
    { href: '/admin/participants', title: 'Participants', hint: 'Registry of trusted participants' },
    { href: '/admin/audit', title: 'Audit log', hint: 'PROV-O events and data flows' },
    { href: '/admin/health', title: 'System health', hint: 'Service liveness' },
  ];
</script>

<svelte:head><title>Operator</title></svelte:head>

<div class="space-y-6">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Operator</h1>
    <p class="text-sm text-gray-500 mt-1">Administration and observability for this participant.</p>
  </div>

  <div class="grid grid-cols-3 gap-4">
    {#each [
      { label: 'Participants', value: data.counts.participants, href: '/admin/participants' },
      { label: 'Published assets', value: data.counts.assets, href: '/provider/assets' },
      { label: 'Agreements', value: data.counts.agreements, href: '/provider/contracts' },
    ] as tile}
      <a href={tile.href} class="ds-card hover:shadow-md transition-shadow">
        <p class="text-xs uppercase tracking-wide text-gray-500">{tile.label}</p>
        <p class="text-2xl font-semibold text-gray-900 mt-1">{show(tile.value)}</p>
        {#if tile.value === null}
          <p class="text-xs text-amber-700 mt-1">unavailable</p>
        {/if}
      </a>
    {/each}
  </div>

  <div>
    <h2 class="font-semibold text-gray-900 mb-2">Recent activity</h2>
    {#if data.eventsError}
      <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-900">
        {data.eventsError}
      </div>
    {:else if (data.recentEvents as AuditEntry[]).length === 0}
      <p class="text-sm text-gray-500">No provenance events recorded yet.</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <tbody class="divide-y divide-gray-100">
            {#each data.recentEvents as e}
              <tr>
                <td class="py-2 pr-4 text-xs text-gray-500 whitespace-nowrap">
                  {new Date(e.occurred_at).toLocaleString()}
                </td>
                <td class="py-2 pr-4">
                  <span class="ds-badge bg-blue-50 text-blue-700">{e.event_type}</span>
                </td>
                <td class="py-2 text-xs text-gray-600 truncate">{e.consumer_did ?? e.provider_did ?? ''}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <a href="/admin/audit" class="text-sm text-brand-600 hover:underline mt-2 inline-block">
        Full audit log →
      </a>
    {/if}
  </div>

  <div>
    <h2 class="font-semibold text-gray-900 mb-2">Sections</h2>
    <div class="grid sm:grid-cols-3 gap-4">
      {#each sections as s}
        <a href={s.href} class="ds-card hover:shadow-md transition-shadow">
          <h3 class="font-semibold text-gray-900">{s.title}</h3>
          <p class="text-sm text-gray-500 mt-1">{s.hint}</p>
        </a>
      {/each}
    </div>
  </div>
</div>
