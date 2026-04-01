<script lang="ts">
  import PolicySummary from '$lib/components/PolicySummary.svelte';
  import JsonLdViewer from '$lib/components/JsonLdViewer.svelte';
  import NegotiationWizard from '$lib/components/NegotiationWizard.svelte';
  import MedallionBadge from '$lib/components/MedallionBadge.svelte';

  let { data } = $props();
  let wizardOpen = $state(false);
  let negotiationResult = $state<{ agreementId: string; transferId: string } | null>(null);

  const d = $derived(data.dataset as Record<string, unknown> | null);
  const title = $derived(d ? String(d['dct:title'] ?? d['title'] ?? data.assetId) : data.assetId);
  const desc = $derived(d ? String(d['dct:description'] ?? d['description'] ?? '') : '');
  const tags = $derived(Array.isArray(d?.['dcat:keyword']) ? (d!['dcat:keyword'] as string[]) : []);
  const providerParticipantId = $derived(String(d?.['dct:publisher'] ?? d?.['provider_id'] ?? ''));
  const medallion = $derived(tags.find((t) => ['bronze', 'silver', 'gold'].includes(t)) ?? '');
</script>

<svelte:head><title>{title}</title></svelte:head>

<div class="max-w-2xl space-y-5">
  <a href="/consumer/catalog" class="text-sm text-brand-600 hover:underline">← Catalog</a>

  {#if data.error || !d}
    <div class="ds-card border-red-200 bg-red-50 text-red-700">{data.error ?? 'Dataset not found'}</div>
  {:else}
    <div class="ds-card space-y-4">
      <div class="flex items-start gap-3 justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">{title}</h1>
          {#if desc}
            <p class="text-gray-600 mt-1">{desc}</p>
          {/if}
        </div>
        <MedallionBadge tier={medallion} />
      </div>

      {#if tags.length > 0}
        <div class="flex flex-wrap gap-1">
          {#each tags as tag}
            <span class="ds-badge bg-gray-100 text-gray-600">{tag}</span>
          {/each}
        </div>
      {/if}

      {#if data.policySummary}
        <div class="border-t border-gray-100 pt-4">
          <h2 class="font-medium text-gray-900 mb-3">Access policy</h2>
          <PolicySummary summary={data.policySummary} />
        </div>
      {/if}

      <JsonLdViewer data={d} label="Full DCAT metadata" />
    </div>

    {#if negotiationResult}
      <div class="ds-card border-green-200 bg-green-50 space-y-1">
        <p class="font-medium text-green-800">Access granted!</p>
        <p class="text-sm text-green-700">Agreement: <code>{negotiationResult.agreementId}</code></p>
        <a href="/consumer/transfers" class="text-sm text-brand-600 hover:underline">View active transfers →</a>
      </div>
    {:else}
      <button class="ds-btn-primary" onclick={() => (wizardOpen = true)}>
        Request access
      </button>
    {/if}

    {#if wizardOpen}
      <NegotiationWizard
        assetId={data.assetId}
        {providerParticipantId}
        policySummary={data.policySummary}
        onClose={() => (wizardOpen = false)}
        onComplete={(r) => {
          negotiationResult = r;
          wizardOpen = false;
        }}
      />
    {/if}
  {/if}
</div>
