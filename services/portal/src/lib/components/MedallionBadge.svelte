<script lang="ts">
  let { tier }: { tier?: string } = $props();

  const styles: Record<string, string> = {
    bronze: 'bg-orange-100 text-orange-800',
    silver: 'bg-gray-100 text-gray-700',
    gold:   'bg-yellow-100 text-yellow-800',
  };
  const icons: Record<string, string> = {
    bronze: '🥉',
    silver: '🥈',
    gold:   '🥇',
  };
  const t = $derived((tier ?? '').toLowerCase());
</script>

{#if t && styles[t]}
  <span class="ds-badge {styles[t]}">
    {icons[t]} {t}
  </span>
{/if}
