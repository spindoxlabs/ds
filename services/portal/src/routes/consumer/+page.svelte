<script lang="ts">
  import { purposeLabel } from '$lib/consent';

  let { data } = $props();
  let queryResult = $state<string | null>(null);
  let queryError = $state<string | null>(null);
  let running = $state(false);

  // The connector reports `awaiting_consent` as a distinct state precisely so it
  // is not read as a stalled negotiation. Showing the raw slug threw that away.
  const STATUS_LABELS: Record<string, string> = {
    awaiting_consent: 'awaiting consent',
    negotiating: 'negotiating',
    finalized: 'agreed',
    transferring: 'transferring',
    transferred: 'delivered',
    revoked: 'withdrawn',
  };

  function statusLabel(status: string): string {
    return STATUS_LABELS[status] ?? status;
  }

  function statusTone(status: string): string {
    if (status === 'awaiting_consent') return 'bg-amber-50 text-amber-800';
    if (status === 'transferred' || status === 'finalized') return 'bg-emerald-50 text-emerald-700';
    if (status === 'revoked') return 'bg-gray-100 text-gray-600';
    return 'bg-blue-50 text-blue-700';
  }


  function fmt(value: unknown): string {
    if (!value) return '-';
    const date = new Date(String(value));
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  async function runQuery(transferId: string) {
    running = true;
    queryResult = null;
    queryError = null;
    try {
      const res = await fetch(`/consumer/transfers/${encodeURIComponent(transferId)}`, { method: 'POST' });
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        throw new Error(text || `Query failed with ${res.status}`);
      }
      queryResult = JSON.stringify(await res.json(), null, 2);
    } catch (e) {
      queryError = e instanceof Error ? e.message : 'Query failed';
    } finally {
      running = false;
    }
  }
</script>

<svelte:head><title>Consumer</title></svelte:head>

<div class="space-y-8">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Consumer</h1>
    <p class="text-sm text-gray-500 mt-1">Contract negotiation status and active EDR transfers for your user.</p>
  </div>

  <section class="space-y-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold text-gray-900">Access Requests</h2>
        <p class="text-sm text-gray-500">Requests started from the catalog, scoped to your authenticated user.</p>
      </div>
      <a href="/" class="ds-btn-primary text-sm">Open catalog</a>
    </div>

    {#if data.revokeError}
      <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.revokeError}</div>
    {/if}

    {#if (data.requests as unknown[]).length === 0}
      <p class="text-gray-500 py-8 text-center">No access requests. Request access from the catalog.</p>
    {:else}
      <div class="space-y-4">
        {#each data.requests as r}
          {@const req = r as Record<string, unknown>}
          <div class="ds-card space-y-3">
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="font-medium text-gray-900">{String(req['asset_id'] ?? '-')}</p>
                <p class="text-sm text-gray-500 mt-0.5">Requested: {fmt(req['created_at'])}</p>
                {#if req['negotiation_id']}
                  <p class="font-mono text-xs text-gray-500 mt-1">Negotiation: {String(req['negotiation_id'])}</p>
                {/if}
                {#if req['transfer_id']}
                  <p class="font-mono text-xs text-gray-500 mt-1">Transfer: {String(req['transfer_id'])}</p>
                {/if}
              </div>
              <span class="ds-badge {statusTone(String(req['status'] ?? ''))}">
                {statusLabel(String(req['status'] ?? '-'))}
              </span>
            </div>
            {#if req['status'] === 'awaiting_consent'}
              <!-- "Not looked at yet" and "waiting on a person, possibly for weeks"
                   render identically without this, which is the distinction that
                   matters most to someone wondering whether to chase it. -->
              <p class="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1">
                Waiting on a data subject to decide{#if req['awaiting_consent_since']}
                  , since {fmt(req['awaiting_consent_since'])}{/if}. Nothing is required
                from you.
              </p>
            {/if}
            <!-- Why this was asked for. The agreement's policy cannot answer it:
                 a multi-purpose offer permits any of its purposes, so the contract
                 says "one of these" and nothing more. -->
            {#if (req['declared_purpose'] as string[] | undefined)?.length || req['declared_until'] || req['justification_ref']}
              <dl class="text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 space-y-1">
                {#if (req['declared_purpose'] as string[] | undefined)?.length}
                  <div class="flex gap-2">
                    <dt class="text-gray-500 w-24 shrink-0">Stated purpose</dt>
                    <dd>{(req['declared_purpose'] as string[]).map(purposeLabel).join(', ')}</dd>
                  </div>
                {/if}
                {#if req['declared_until']}
                  <div class="flex gap-2">
                    <dt class="text-gray-500 w-24 shrink-0">Needed until</dt>
                    <dd>{fmt(req['declared_until'])}</dd>
                  </div>
                {/if}
                {#if req['justification_ref']}
                  <div class="flex gap-2">
                    <dt class="text-gray-500 w-24 shrink-0">Reference</dt>
                    <dd class="font-mono">{String(req['justification_ref'])}</dd>
                  </div>
                {/if}
              </dl>
            {/if}
            <div class="flex items-center gap-2 text-xs text-gray-500">
              {#if req['negotiation_state']}
                <span>Negotiation {String(req['negotiation_state'])}</span>
              {/if}
              {#if req['transfer_state']}
                <span>Transfer {String(req['transfer_state'])}</span>
              {/if}
            </div>
            {#if req['can_revoke']}
              <form method="POST" action="?/revoke">
                <input type="hidden" name="request_id" value={String(req['id'])} />
                <button class="ds-btn-secondary text-sm" type="submit">Revoke access</button>
              </form>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <section class="space-y-4">
    <div>
      <h2 class="text-lg font-semibold text-gray-900">Active Transfers</h2>
      <p class="text-sm text-gray-500">Started transfers scoped to your authenticated user.</p>
    </div>

    {#if data.error}
      <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
    {:else if (data.transfers as unknown[]).length === 0}
      <p class="text-gray-500 py-8 text-center">No active transfers. Request access from the catalog.</p>
    {:else}
      <div class="space-y-4">
        {#each data.transfers as t}
          {@const transfer = t as Record<string, unknown>}
          <div class="ds-card space-y-3">
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="font-mono text-sm text-gray-700">{String(transfer['transfer_id'] ?? transfer['id'] ?? '-')}</p>
                <p class="text-sm text-gray-500 mt-0.5">Asset: {String(transfer['asset_id'] ?? '-')}</p>
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
                  onclick={() => runQuery(String(transfer['transfer_id']))}
                >
                  {running ? 'Querying...' : 'Run query'}
                </button>
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </section>

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
