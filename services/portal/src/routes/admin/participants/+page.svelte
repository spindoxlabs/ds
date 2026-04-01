<script lang="ts">
  let { data } = $props();
</script>

<svelte:head><title>Participants</title></svelte:head>

<div class="space-y-5">
  <h1 class="text-xl font-bold text-gray-900">Participant Registry</h1>

  {#if data.error}
    <div class="ds-card border-amber-200 bg-amber-50 text-amber-700 text-sm">
      Could not load participants from connector: {data.error}
    </div>
    <p class="text-sm text-gray-500">
      Manage participants directly in <code class="bg-gray-100 px-1 rounded">governance/participants.yaml</code>.
    </p>
  {:else if (data.participants as unknown[]).length === 0}
    <p class="text-gray-500 py-8 text-center">No participants registered.</p>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left border-b border-gray-200 text-gray-500 text-xs uppercase">
            <th class="pb-2 pr-4">ID</th>
            <th class="pb-2 pr-4">DSP Endpoint</th>
            <th class="pb-2">Scopes</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {#each data.participants as p}
            {@const participant = p as Record<string, unknown>}
            <tr>
              <td class="py-2 pr-4 font-mono text-xs text-gray-700">{String(participant['id'] ?? participant['participant_id'] ?? '—')}</td>
              <td class="py-2 pr-4 text-xs text-gray-600">{String(participant['dsp_endpoint'] ?? '—')}</td>
              <td class="py-2 text-xs text-gray-600">{String(participant['scopes'] ?? '—')}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
