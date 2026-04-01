<script lang="ts">
</script>

<svelte:head><title>Provider</title></svelte:head>

<div class="space-y-4">
  <h1 class="text-xl font-bold text-gray-900">Provider Dashboard</h1>
  <div class="grid sm:grid-cols-3 gap-4">
    <a href="/provider/assets" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Assets</h2>
      <p class="text-sm text-gray-500 mt-1">Manage and sync dataset offerings</p>
    </a>
    <a href="/provider/contracts" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Contracts</h2>
      <p class="text-sm text-gray-500 mt-1">View active and past agreements</p>
    </a>
    <a href="/provider/governance" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Governance</h2>
      <p class="text-sm text-gray-500 mt-1">Policy configuration</p>
    </a>
  </div>
</div>
