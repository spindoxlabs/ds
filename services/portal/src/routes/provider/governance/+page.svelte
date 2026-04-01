<script lang="ts">
  // governance.yaml viewer — static, rendered from connector's /provider/assets enriched with policy info
  let { data } = $props();
</script>

<svelte:head><title>Governance Policies</title></svelte:head>

<div class="space-y-5">
  <h1 class="text-xl font-bold text-gray-900">Governance Policies</h1>
  <p class="text-sm text-gray-600">
    Policies are managed in <code class="bg-gray-100 px-1 rounded">governance.yaml</code> and synced to EDC via
    <a href="/provider/assets" class="text-brand-600 hover:underline">Provider Assets → Sync governance</a>.
  </p>
  <div class="ds-card bg-gray-50">
    <p class="text-sm text-gray-500 italic">
      Edit <code>governance/governance.yaml</code> in your deployment, then click "Sync governance" to push changes.
    </p>
  </div>
</div>
