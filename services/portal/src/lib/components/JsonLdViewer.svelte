<script lang="ts">
  let { data, label = 'Raw JSON-LD' }: { data: unknown; label?: string } = $props();
  let open = $state(false);
  const json = $derived(JSON.stringify(data, null, 2));
</script>

<details bind:open class="mt-2">
  <summary class="cursor-pointer text-sm text-gray-500 hover:text-gray-700 select-none">
    {open ? '▾' : '▸'} {label}
  </summary>
  <pre class="mt-2 text-xs bg-gray-900 text-green-300 rounded-lg p-3 overflow-x-auto max-h-64 overflow-y-auto">{json}</pre>
</details>
