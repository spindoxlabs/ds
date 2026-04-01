<script lang="ts">
</script>

<svelte:head><title>Consumer</title></svelte:head>

<div class="space-y-4">
  <h1 class="text-xl font-bold text-gray-900">Consumer Dashboard</h1>
  <div class="grid sm:grid-cols-3 gap-4">
    <a href="/consumer/catalog" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Catalog</h2>
      <p class="text-sm text-gray-500 mt-1">Browse available datasets</p>
    </a>
    <a href="/consumer/negotiations" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Negotiations</h2>
      <p class="text-sm text-gray-500 mt-1">Track contract negotiations</p>
    </a>
    <a href="/consumer/transfers" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Transfers</h2>
      <p class="text-sm text-gray-500 mt-1">Active EDR transfers + query runner</p>
    </a>
  </div>
</div>
