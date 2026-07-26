<script lang="ts">
  import type { AuditEntry } from '$lib/server/provenance';

  interface Props {
    events: AuditEntry[];
    total: number;
    limit: number;
    offset: number;
    /** Rendered as links to the lineage graph when the event names a data product. */
    lineage?: boolean;
  }

  let { events, total, limit, offset, lineage = true }: Props = $props();

  let expanded = $state<string | null>(null);

  // Event types differ in what they carry, so a fixed column set would either be
  // mostly empty or hide the fields that matter. The table shows the dimensions
  // every event shares; the rest expands per row.
  function shortDid(value: string | undefined): string {
    if (!value) return '';
    if (value === '*') return 'any party in the circle';
    const tail = value.split(':').pop() ?? value;
    return tail.length > 28 ? tail.slice(0, 26) + '…' : tail;
  }

  function formatDetailValue(value: unknown): string {
    if (Array.isArray(value)) return value.map((v) => formatDetailValue(v)).join(', ');
    if (value && typeof value === 'object') {
      return Object.entries(value as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${formatDetailValue(v)}`)
        .join(' · ');
    }
    return String(value);
  }

  function label(key: string): string {
    return key.replace(/_/g, ' ');
  }

  const from = $derived(total === 0 ? 0 : offset + 1);
  const to = $derived(Math.min(offset + limit, total));

  function pageHref(newOffset: number): string {
    const params = new URLSearchParams(
      typeof window === 'undefined' ? '' : window.location.search,
    );
    params.set('offset', String(Math.max(0, newOffset)));
    return `?${params}`;
  }
</script>

{#if events.length === 0}
  <p class="text-sm text-gray-500 py-6 text-center">No events match this view.</p>
{:else}
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left border-b border-gray-200 text-gray-500 text-xs uppercase">
          <th class="pb-2 pr-4">When</th>
          <th class="pb-2 pr-4">Event</th>
          <th class="pb-2 pr-4">Data product</th>
          <th class="pb-2 pr-4">Party</th>
          <th class="pb-2"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">
        {#each events as e (e.id)}
          <tr>
            <td class="py-2 pr-4 text-xs text-gray-500 whitespace-nowrap">
              {new Date(e.occurred_at).toLocaleString()}
            </td>
            <td class="py-2 pr-4">
              <span class="ds-badge bg-blue-50 text-blue-700">{e.event_type}</span>
            </td>
            <td class="py-2 pr-4 text-xs text-gray-600">
              {#if e.data_product_id && lineage}
                <a
                  class="text-brand-600 hover:underline"
                  href="/lineage/{encodeURIComponent(e.data_product_id)}"
                >{e.data_product_id}</a>
              {:else}
                {e.data_product_id ?? '—'}
              {/if}
            </td>
            <td class="py-2 pr-4 text-xs text-gray-600" title={e.consumer_did ?? e.provider_did ?? ''}>
              {shortDid(e.consumer_did ?? e.provider_did) || '—'}
            </td>
            <td class="py-2 text-right">
              {#if Object.keys(e.detail).length > 0}
                <button
                  class="text-xs text-brand-600 hover:underline"
                  onclick={() => (expanded = expanded === e.id ? null : e.id)}
                >{expanded === e.id ? 'Hide' : 'Details'}</button>
              {/if}
            </td>
          </tr>
          {#if expanded === e.id}
            <tr class="bg-gray-50">
              <td colspan="5" class="py-3 px-4">
                <dl class="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-xs">
                  {#each Object.entries(e.detail) as [key, value]}
                    <div class="flex gap-2">
                      <dt class="text-gray-500 shrink-0">{label(key)}</dt>
                      <dd class="text-gray-800 font-mono break-all">{formatDetailValue(value)}</dd>
                    </div>
                  {/each}
                </dl>
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>

  <div class="flex items-center justify-between mt-3 text-xs text-gray-500">
    <span>Showing {from}–{to} of {total}</span>
    <div class="flex gap-2">
      {#if offset > 0}
        <a class="ds-btn-secondary text-xs" href={pageHref(offset - limit)}>Previous</a>
      {/if}
      {#if to < total}
        <a class="ds-btn-secondary text-xs" href={pageHref(offset + limit)}>Next</a>
      {/if}
    </div>
  </div>
{/if}
