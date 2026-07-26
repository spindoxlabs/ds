<script lang="ts">
  import ConsentBadge from '$lib/components/ConsentBadge.svelte';
  import { WILDCARD_CONSUMER } from '$lib/consent';
  import type { ConsentRequest } from '$lib/server/connector';

  let { data } = $props();

  type Ask = ConsentRequest & {
    negotiation_id?: string | null;
    correlation_id?: string | null;
    negotiation_closed_at?: string | null;
  };

  const asks = $derived(data.asks as Ask[]);

  function waitingSince(ask: Ask): string {
    if (!ask.requested_at) return '';
    const days = Math.floor((Date.now() - new Date(ask.requested_at).getTime()) / 86_400_000);
    if (days <= 0) return 'today';
    return days === 1 ? '1 day' : `${days} days`;
  }

  const FILTERS = [
    { value: 'pending', label: 'Awaiting a decision' },
    { value: 'granted', label: 'Granted' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'all', label: 'All' },
  ];
</script>

<svelte:head><title>Consent requests</title></svelte:head>

<div class="space-y-5">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Consent requests</h1>
    <p class="text-sm text-gray-600 mt-1">
      Which consent decision is holding up which negotiation. A consumer asks by
      negotiating — the request is recorded here from the identity DSP already
      carries, and the subject decides through their own pages.
    </p>
  </div>

  <div class="flex gap-2">
    {#each FILTERS as f}
      <a
        href="?status={f.value}"
        class="ds-badge {data.status === f.value ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-700'}"
      >{f.label}</a>
    {/each}
  </div>

  {#if data.error}
    <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-900">{data.error}</div>
  {:else if asks.length === 0}
    <p class="text-sm text-gray-500 py-6 text-center">
      Nothing is waiting on a consent decision.
    </p>
  {:else}
    <div class="grid gap-3">
      {#each asks as ask (ask.id)}
        <article class="ds-card space-y-2">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="font-medium text-gray-900">{ask.dataset_id}</p>
              <p class="text-sm text-gray-600 mt-0.5">
                Asked by
                {#if ask.consumer_id === WILDCARD_CONSUMER}
                  any party in the circle
                {:else}
                  <span class="font-mono text-xs">{ask.consumer_id}</span>
                {/if}
                {#if ask.purpose?.length}
                  for {ask.purpose.join(', ')}
                {/if}
              </p>
            </div>
            <ConsentBadge status={ask.status} />
          </div>

          <dl class="grid gap-x-6 gap-y-1 text-xs text-gray-600 sm:grid-cols-2">
            <div>
              <dt class="inline text-gray-500">Subject:</dt>
              <dd class="inline font-mono break-all"> {ask.subject_id}</dd>
            </div>
            <div>
              <dt class="inline text-gray-500">Waiting:</dt>
              <dd class="inline"> {waitingSince(ask)}</dd>
            </div>
            {#if ask.controller}
              <div>
                <dt class="inline text-gray-500">Controller:</dt>
                <dd class="inline"> {ask.controller}{#if ask.controller_role} ({ask.controller_role}){/if}</dd>
              </div>
            {/if}
            {#if ask.negotiation_id}
              <div class="sm:col-span-2">
                <!-- The join key between a parked negotiation and the decision it
                     waits on. Without it an operator cannot answer "why is this
                     consumer's request stuck". -->
                <dt class="inline text-gray-500">Blocking negotiation:</dt>
                <dd class="inline font-mono break-all"> {ask.negotiation_id}</dd>
              </div>
            {/if}
          </dl>

          {#if ask.status === 'pending'}
            <p class="text-xs text-gray-500">
              The subject decides this — it is not an approval you can give. They see
              it under “My consents”.
            </p>
          {/if}
        </article>
      {/each}
    </div>
  {/if}
</div>
