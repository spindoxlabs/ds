<script lang="ts">
  let { data } = $props();

  // null means "could not be read", which is not the same as zero.
  function show(value: number | null): string {
    return value === null ? '—' : String(value);
  }

  const sections = [
    { href: '/provider/assets', title: 'Datasets', hint: 'What is published, and its sync state' },
    { href: '/provider/contracts', title: 'Agreements', hint: 'Active and past contracts' },
    { href: '/provider/requests', title: 'Consent requests', hint: 'Which decision is holding up which negotiation' },
    { href: '/provider/activity', title: 'Activity', hint: 'What happened to the data you publish' },
  ];
</script>

<svelte:head><title>Provider</title></svelte:head>

<div class="space-y-6">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Provider</h1>
    <p class="text-sm text-gray-500 mt-1">What this participant offers, and who is asking for it.</p>
  </div>

  <div class="grid grid-cols-3 gap-4">
    <a href="/provider/assets" class="ds-card hover:shadow-md transition-shadow">
      <p class="text-xs uppercase tracking-wide text-gray-500">Published datasets</p>
      <p class="text-2xl font-semibold text-gray-900 mt-1">{show(data.counts.assets)}</p>
    </a>
    <a href="/provider/contracts" class="ds-card hover:shadow-md transition-shadow">
      <p class="text-xs uppercase tracking-wide text-gray-500">Transfers</p>
      <p class="text-2xl font-semibold text-gray-900 mt-1">{show(data.counts.transfers)}</p>
    </a>
    <a href="/provider/requests" class="ds-card hover:shadow-md transition-shadow {data.counts.pendingAsks ? 'border-amber-200 bg-amber-50' : ''}">
      <p class="text-xs uppercase tracking-wide text-gray-500">Awaiting a consent decision</p>
      <p class="text-2xl font-semibold text-gray-900 mt-1">{show(data.counts.pendingAsks)}</p>
      {#if data.counts.pendingAsks}
        <p class="text-xs text-amber-900 mt-1">
          A negotiation is parked until a data subject decides.
        </p>
      {/if}
    </a>
  </div>

  <div>
    <h2 class="font-semibold text-gray-900 mb-2">Sections</h2>
    <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {#each sections as s}
        <a href={s.href} class="ds-card hover:shadow-md transition-shadow">
          <h3 class="font-semibold text-gray-900">{s.title}</h3>
          <p class="text-sm text-gray-500 mt-1">{s.hint}</p>
        </a>
      {/each}
    </div>
    {#if !data.may.sync}
      <p class="text-xs text-gray-500 mt-3">
        You have read access. Syncing governance needs
        <code class="bg-gray-100 px-1 rounded">connector.provider.write</code>.
      </p>
    {/if}
  </div>
</div>
