<script lang="ts">
  import EventTable from '$lib/components/EventTable.svelte';
  import type { AuditEntry } from '$lib/server/provenance';

  let { data } = $props();

  // Every type the provenance service can record. Listing them explicitly beats a
  // free-text box: an operator filtering by a typo silently sees nothing.
  const EVENT_TYPES = [
    'CataloguePublished', 'CatalogViewed', 'AccessRequested',
    'NegotiationStarted', 'NegotiationFinalized', 'NegotiationTerminated',
    'ContractAgreementSigned', 'TransferStarted', 'DataTransferCompleted',
    'QueryExecuted', 'AccessRevoked',
    'ConsentGranted', 'ConsentRevoked', 'DataIngested', 'DataDisclosed',
  ];

  const selected = $derived(new Set(data.query.event_type ?? []));

  /**
   * Export what is on screen, not a fixed five columns.
   *
   * Event types carry different fields, so the union of the visible page is the
   * honest set — a fixed header drops exactly the columns that make the Block C
   * events meaningful.
   */
  function exportCsv() {
    const events = data.page.events as AuditEntry[];
    if (events.length === 0) return;

    const detailKeys = [...new Set(events.flatMap((e) => Object.keys(e.detail)))].sort();
    const header = [
      'occurred_at', 'event_type', 'data_product_id', 'agreement_id',
      'provider_did', 'consumer_did', 'subject_id', ...detailKeys,
    ];

    const cell = (value: unknown): string => {
      if (value === undefined || value === null) return '';
      const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
      return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };

    const rows = events.map((e) =>
      header
        .map((key) =>
          cell(key in e.detail ? e.detail[key] : (e as unknown as Record<string, unknown>)[key]),
        )
        .join(','),
    );

    const blob = new Blob([[header.join(','), ...rows].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'provenance-events.csv';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<svelte:head><title>Observability</title></svelte:head>

<div class="space-y-5">
  <div class="flex items-start justify-between gap-4">
    <div>
      <h1 class="text-xl font-bold text-gray-900">Observability</h1>
      <p class="text-sm text-gray-500 mt-1">
        Every provenance event this participant recorded.
      </p>
    </div>
    <button class="ds-btn-secondary text-sm shrink-0" onclick={exportCsv}>Export CSV</button>
  </div>

  <form method="GET" class="ds-card space-y-3">
    <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <label class="text-xs text-gray-600">
        Data product
        <input
          class="ds-input mt-1 w-full" type="text" name="dataset_id"
          value={data.query.dataset_id ?? ''} placeholder="datasets.silver.meters_15m"
        />
      </label>
      <label class="text-xs text-gray-600">
        Subject DID
        <input
          class="ds-input mt-1 w-full" type="text" name="subject_id"
          value={data.query.subject_id ?? ''} placeholder="did:web:…"
        />
      </label>
      <label class="text-xs text-gray-600">
        From
        <input
          class="ds-input mt-1 w-full" type="date" name="occurred_after"
          value={(data.query.occurred_after ?? '').slice(0, 10)}
        />
      </label>
      <label class="text-xs text-gray-600">
        To
        <input
          class="ds-input mt-1 w-full" type="date" name="occurred_before"
          value={(data.query.occurred_before ?? '').slice(0, 10)}
        />
      </label>
    </div>

    <fieldset>
      <legend class="text-xs text-gray-600 mb-1">Event types</legend>
      <div class="flex flex-wrap gap-x-4 gap-y-1">
        {#each EVENT_TYPES as type}
          <label class="text-xs text-gray-700 flex items-center gap-1">
            <input type="checkbox" name="event_type" value={type} checked={selected.has(type)} />
            {type}
          </label>
        {/each}
      </div>
    </fieldset>

    <div class="flex gap-2">
      <button class="ds-btn-primary text-sm" type="submit">Apply</button>
      <a class="ds-btn-secondary text-sm" href="/admin/observability">Clear</a>
    </div>
  </form>

  {#if data.error}
    <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-900">{data.error}</div>
  {:else}
    <EventTable
      events={data.page.events}
      total={data.page.total}
      limit={data.page.limit}
      offset={data.page.offset}
    />
  {/if}
</div>
