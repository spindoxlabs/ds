<script lang="ts">
  let { status }: { status: string } = $props();

  const styles: Record<string, string> = {
    pending:  'bg-yellow-100 text-yellow-800',
    granted:  'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
    revoked:  'bg-gray-100 text-gray-600',
  };
  const labels: Record<string, string> = {
    pending:  'Pending',
    granted:  'Granted',
    rejected: 'Rejected',
    revoked:  'Revoked',
  };
</script>

<span class="ds-badge {styles[status] ?? 'bg-gray-100 text-gray-600'}">
  {labels[status] ?? status}
</span>
