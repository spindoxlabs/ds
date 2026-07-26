<script lang="ts">
  import EventTable from '$lib/components/EventTable.svelte';
  let { data } = $props();
</script>

<svelte:head><title>Consumer activity</title></svelte:head>

<div class="space-y-5">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Consumer activity</h1>
    <p class="text-sm text-gray-500 mt-1">What this participant has requested, negotiated and received.</p>
  </div>

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
