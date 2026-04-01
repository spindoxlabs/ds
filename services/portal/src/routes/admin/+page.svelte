<script lang="ts">
</script>

<svelte:head><title>Admin</title></svelte:head>

<div class="space-y-4">
  <h1 class="text-xl font-bold text-gray-900">Operator Panel</h1>
  <div class="grid sm:grid-cols-3 gap-4">
    <a href="/admin/participants" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Participants</h2>
      <p class="text-sm text-gray-500 mt-1">Registry of trusted participants</p>
    </a>
    <a href="/admin/audit" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">Audit Log</h2>
      <p class="text-sm text-gray-500 mt-1">PROV-O events and data flows</p>
    </a>
    <a href="/admin/health" class="ds-card hover:shadow-md transition-shadow">
      <h2 class="font-semibold text-gray-900">System Health</h2>
      <p class="text-sm text-gray-500 mt-1">Service liveness status</p>
    </a>
  </div>
</div>
