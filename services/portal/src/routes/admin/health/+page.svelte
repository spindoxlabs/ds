<script lang="ts">
  let { data } = $props();
</script>

<svelte:head><title>System Health</title></svelte:head>

<div class="space-y-5">
  <h1 class="text-xl font-bold text-gray-900">System Health</h1>
  <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
    {#each data.services as svc}
      <div class="ds-card flex items-start gap-3">
        <div class="mt-0.5">
          {#if svc.status === 'ok'}
            <span class="w-3 h-3 rounded-full bg-green-500 inline-block"></span>
          {:else}
            <span class="w-3 h-3 rounded-full bg-red-500 inline-block"></span>
          {/if}
        </div>
        <div>
          <p class="font-medium text-gray-900">{svc.name}</p>
          <p class="text-xs text-gray-500 font-mono mt-0.5">{svc.url}</p>
          {#if svc.detail}
            <p class="text-xs text-gray-400 mt-1">{svc.detail}</p>
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>
