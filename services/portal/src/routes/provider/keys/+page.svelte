<script lang="ts">
  import { causeLabel, pageHref, plainList } from '$lib/holder-keys';

  let { data } = $props();

  let copied = $state(false);

  function when(value: string | null): string {
    return value ? new Date(value).toLocaleString() : '—';
  }

  async function copyList() {
    if (!data.keys) return;
    await navigator.clipboard.writeText(plainList(data.keys.keys));
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }
</script>

<svelte:head><title>Authorised keys</title></svelte:head>

<div class="space-y-5">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Authorised keys</h1>
    <p class="text-sm text-gray-600 mt-1">
      The data keys — supply points, for example — whose release this participant's
      connector currently authorises, per sharing offer, and the history of each
      authorisation. Keys only: who stands behind a key is never shown here.
    </p>
  </div>

  {#if data.offers.length === 0 && !data.error}
    <p class="text-sm text-gray-500 py-6 text-center">
      This connector serves no dataset under a consent-based offer, so it holds no keys.
    </p>
  {:else}
    <div class="flex flex-wrap gap-2" aria-label="Sharing offer">
      {#each data.offers as offer (offer.id)}
        <a
          href={pageHref(offer.id, data.tab)}
          class="ds-badge {data.offerId === offer.id ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-700'}"
        >{offer.id}</a>
      {/each}
    </div>
  {/if}

  {#if data.offerId}
    <div class="flex gap-4 border-b border-gray-200 text-sm" role="tablist">
      <a
        role="tab"
        aria-selected={data.tab === 'current'}
        href={pageHref(data.offerId, 'current')}
        class="pb-2 {data.tab === 'current' ? 'border-b-2 border-brand-600 font-medium text-gray-900' : 'text-gray-500'}"
      >Authorised now</a>
      <a
        role="tab"
        aria-selected={data.tab === 'history'}
        href={pageHref(data.offerId, 'history')}
        class="pb-2 {data.tab === 'history' ? 'border-b-2 border-brand-600 font-medium text-gray-900' : 'text-gray-500'}"
      >History</a>
    </div>
  {/if}

  {#if data.error}
    <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-900">{data.error}</div>
  {:else if data.keys}
    {@const keys = data.keys}
    <div class="ds-card text-sm text-gray-700 space-y-1">
      <p>
        Released to <strong>{keys.recipient}</strong>{#if keys.recipient_role} ({keys.recipient_role}){/if}
        for {keys.purpose.join(', ')}.
      </p>
      {#each keys.datasets as ds (ds.dataset_id)}
        <p>
          <span class="font-mono text-xs">{ds.dataset_id}</span>:
          <strong data-testid="key-count">{ds.key_count}</strong> key{ds.key_count === 1 ? '' : 's'}
        </p>
        {#if ds.grants_without_keys}
          <p class="text-xs text-amber-900">
            Some standing consent here was registered without a key, so nothing is
            released for it. The collecting organisation has to register it again
            with the key.
          </p>
        {/if}
      {/each}
    </div>

    {#if keys.keys.length === 0}
      <p class="text-sm text-gray-500 py-6 text-center">No key is authorised under this offer.</p>
    {:else}
      <div class="flex justify-end">
        <button type="button" class="ds-badge bg-gray-100 text-gray-700" onclick={copyList}>
          {copied ? 'Copied' : 'Copy values, one per line'}
        </button>
      </div>
      <table class="w-full text-sm" data-testid="holder-keys">
        <thead class="text-left text-xs uppercase tracking-wide text-gray-500">
          <tr><th class="py-2">Type</th><th>Value</th><th>Dataset</th><th>Authorised since</th></tr>
        </thead>
        <tbody>
          {#each keys.keys as k (k.dataset_id + k.key)}
            <tr class="border-t border-gray-100">
              <td class="py-2">{k.key_type}</td>
              <td class="font-mono">{k.value}</td>
              <td class="font-mono text-xs">{k.dataset_id}</td>
              <td>{when(k.authorised_since)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if keys.next_cursor}
        <a class="text-sm text-brand-600" href={pageHref(keys.offer_id, 'current', keys.next_cursor)}>Next page →</a>
      {/if}
    {/if}
  {:else if data.history}
    {@const history = data.history}
    <p class="text-xs text-gray-500">{history.note}</p>
    {#if history.events.length === 0}
      <p class="text-sm text-gray-500 py-6 text-center">Nothing has happened under this offer yet.</p>
    {:else}
      <table class="w-full text-sm" data-testid="holder-key-events">
        <thead class="text-left text-xs uppercase tracking-wide text-gray-500">
          <tr><th class="py-2">When</th><th>Key</th><th>Change</th><th>Why</th><th>By</th></tr>
        </thead>
        <tbody>
          {#each history.events as e, i (e.at + e.key + i)}
            <tr class="border-t border-gray-100">
              <td class="py-2">{when(e.at)}</td>
              <td class="font-mono">{e.key}</td>
              <td>
                <span class="ds-badge {e.event === 'added' ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-800'}">
                  {e.event === 'added' ? 'authorised' : 'no longer authorised'}
                </span>
              </td>
              <td>{causeLabel(e.cause)}</td>
              <td class="text-xs">
                {e.decided_by ?? '—'}{#if e.collector}<br /><span class="font-mono">{e.collector}</span>{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <p class="text-xs text-gray-500">
        The history records decisions. A key two decisions carry stays authorised when
        one of them is withdrawn — “Authorised now” is the list to act on.
      </p>
      {#if history.next_cursor}
        <a class="text-sm text-brand-600" href={pageHref(history.offer_id, 'history', history.next_cursor)}>Next page →</a>
      {/if}
    {/if}
  {/if}
</div>
