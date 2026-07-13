<script lang="ts">
  import ConsentBadge from '$lib/components/ConsentBadge.svelte';
  import type { ConsentRequest } from '$lib/server/connector';

  let { data } = $props();

  const pending = $derived((data.consents as ConsentRequest[]).filter((c) => c.status === 'pending'));
  const active = $derived((data.consents as ConsentRequest[]).filter((c) => c.status === 'granted'));
  const historical = $derived(
    (data.consents as ConsentRequest[]).filter((c) => c.status === 'rejected' || c.status === 'revoked'),
  );

  function timeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins} minute${mins !== 1 ? 's' : ''} ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hour${hrs !== 1 ? 's' : ''} ago`;
    const days = Math.floor(hrs / 24);
    return `${days} day${days !== 1 ? 's' : ''} ago`;
  }
</script>

<svelte:head>
  <title>My Data Consents</title>
</svelte:head>

<div class="max-w-xl mx-auto space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-xl font-bold text-gray-900">My Data Consents</h1>
    <span class="text-2xl">🔔</span>
  </div>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-red-700 text-sm">{data.error}</div>
  {/if}

  <!-- Pending requests -->
  {#if pending.length > 0}
    <section>
      <div class="flex items-center gap-2 mb-3">
        <span class="w-2 h-2 rounded-full bg-yellow-500"></span>
        <h2 class="font-medium text-gray-700">{pending.length} pending request{pending.length !== 1 ? 's' : ''}</h2>
      </div>
      <div class="space-y-3">
        {#each pending as consent}
          <div class="ds-card">
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="font-medium text-gray-900">{consent.consumer_id}</p>
                <p class="text-sm text-gray-600 mt-0.5">Dataset: {consent.dataset_id}</p>
                {#if consent.purpose?.length}
                  <p class="text-sm text-gray-600">Purpose: {consent.purpose.join(', ')}</p>
                {/if}
                <p class="text-xs text-gray-400 mt-1">Requested: {timeAgo(consent.requested_at)}</p>
              </div>
              <ConsentBadge status={consent.status} />
            </div>
            <div class="mt-3">
              <a href="/consent/{consent.id}" class="ds-btn-primary text-sm">View details</a>
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Active consents -->
  {#if active.length > 0}
    <section>
      <h2 class="font-medium text-gray-700 mb-3 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-green-500"></span>
        Active consents
      </h2>
      <div class="space-y-3">
        {#each active as consent}
          <div class="ds-card">
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="font-medium text-gray-900">{consent.consumer_id}</p>
                <p class="text-sm text-gray-600">Dataset: {consent.dataset_id}</p>
                <p class="text-xs text-gray-400 mt-1">
                  Since: {new Date(consent.decided_at ?? consent.requested_at).toLocaleDateString()}
                </p>
              </div>
              <ConsentBadge status={consent.status} />
            </div>
            <div class="mt-3 flex gap-2">
              <a href="/consent/{consent.id}" class="ds-btn-secondary text-sm">Details</a>
              <form method="POST" action="/consent/{consent.id}?/revoke">
                <button type="submit" class="ds-btn-danger text-sm">Revoke</button>
              </form>
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Historical -->
  {#if historical.length > 0}
    <section>
      <h2 class="font-medium text-gray-500 mb-3 text-sm">Past requests</h2>
      <div class="space-y-2">
        {#each historical as consent}
          <div class="ds-card opacity-70">
            <div class="flex items-center justify-between gap-2">
              <div>
                <p class="text-sm font-medium text-gray-700">{consent.consumer_id}</p>
                <p class="text-xs text-gray-500">{consent.dataset_id}</p>
              </div>
              <ConsentBadge status={consent.status} />
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if data.consents.length === 0 && !data.error}
    <div class="text-center py-12 text-gray-500">
      <p class="text-4xl mb-3">📋</p>
      <p>No consent requests yet.</p>
    </div>
  {/if}
</div>
