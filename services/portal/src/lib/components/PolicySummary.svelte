<script lang="ts">
  import type { PolicySummary } from '$lib/server/odrl';

  let { summary }: { summary: PolicySummary } = $props();
</script>

<div class="space-y-3 text-sm">
  {#if summary.permitted.length > 0}
    <div>
      <p class="font-medium text-gray-700 mb-1">Permitted actions</p>
      <ul class="space-y-1">
        {#each summary.permitted as action}
          <li class="flex items-center gap-2 text-green-700">
            <span class="text-green-500">✓</span>
            {action}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if summary.prohibited.length > 0}
    <div>
      <p class="font-medium text-gray-700 mb-1">Prohibited actions</p>
      <ul class="space-y-1">
        {#each summary.prohibited as action}
          <li class="flex items-center gap-2 text-red-700">
            <span class="text-red-500">✗</span>
            {action}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if summary.obligations.length > 0}
    <div>
      <p class="font-medium text-gray-700 mb-1">Obligations</p>
      <ul class="space-y-1">
        {#each summary.obligations as ob}
          <li class="flex items-center gap-2 text-amber-700">
            <span class="text-amber-500">!</span>
            {ob}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if summary.constraints.length > 0}
    <div>
      <p class="font-medium text-gray-700 mb-1">Conditions</p>
      <ul class="space-y-1">
        {#each summary.constraints as c}
          <li class="text-gray-600 pl-4 border-l-2 border-gray-200">{c}</li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if summary.permitted.length === 0 && summary.prohibited.length === 0 && summary.obligations.length === 0}
    <p class="text-gray-400 italic">No policy details available.</p>
  {/if}
</div>
