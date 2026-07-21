<script lang="ts">
  import PolicySummary from '$lib/components/PolicySummary.svelte';
  import JsonLdViewer from '$lib/components/JsonLdViewer.svelte';
  import NegotiationWizard from '$lib/components/NegotiationWizard.svelte';
  let { data } = $props();
  let wizardOpen = $state(false);
  let negotiationResult = $state<{ agreementId: string; transferId: string } | null>(null);

  const d = $derived(data.dataset as Record<string, unknown> | null);
  const title = $derived(d ? String(d['dct:title'] ?? d['title'] ?? data.assetId) : data.assetId);
  const desc = $derived(d ? String(d['dct:description'] ?? d['description'] ?? '') : '');
  const tags = $derived(Array.isArray(d?.['dcat:keyword']) ? (d!['dcat:keyword'] as string[]) : []);

  function dstr(...keys: string[]): string {
    if (!d) return '';
    for (const k of keys) {
      const v = d[k];
      if (v && typeof v === 'string') return v;
      if (v && typeof v === 'object' && '@id' in (v as Record<string, unknown>))
        return String((v as Record<string, unknown>)['@id']);
    }
    return '';
  }
  const accessLevel = $derived(dstr('ds:accessLevel', 'access_level', 'accessRights'));
  const classification = $derived(dstr('ds:classification'));
  const sourceSystem = $derived(dstr('ds:sourceSystem'));
  const publisher = $derived(dstr('dct:publisher'));
  const negotiation = $derived(data.negotiation as {
    counterPartyAddress: string;
    offerId: string;
    assigner: string;
    odrlPolicy: Record<string, unknown> | null;
  } | null);
  const existingRequest = $derived(data.existingRequest as Record<string, unknown> | null);
  const activeExistingRequest = $derived.by(() => {
    if (!existingRequest) return null;
    const status = String(existingRequest['status'] ?? '').trim().toLowerCase();
    return ['negotiating', 'finalized', 'transferring', 'transferred'].includes(status)
      ? existingRequest
      : null;
  });

</script>

<svelte:head><title>{title}</title></svelte:head>

<div class="max-w-2xl space-y-5">
  <a href="/" class="text-sm text-brand-600 hover:underline">← Catalog</a>

  {#if data.error || !d}
    <div class="ds-card border-red-200 bg-red-50 text-red-700">{data.error ?? 'Dataset not found'}</div>
  {:else}
    <div class="ds-card space-y-4">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">{title}</h1>
        {#if desc}
          <p class="text-gray-600 mt-1">{desc}</p>
        {/if}
      </div>

      {#if accessLevel || classification || sourceSystem || publisher || negotiation?.assigner}
        <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {#if negotiation?.assigner}
            <dt class="text-gray-500">Data Owner</dt>
            <dd class="font-medium text-gray-700" title={negotiation.assigner}>{negotiation.assigner}</dd>
          {/if}
          {#if accessLevel}
            <dt class="text-gray-500">Access Level</dt>
            <dd><span class="ds-badge bg-blue-50 text-blue-700">{accessLevel}</span></dd>
          {/if}
          {#if classification}
            <dt class="text-gray-500">Classification</dt>
            <dd><span class="ds-badge bg-purple-50 text-purple-700">{classification}</span></dd>
          {/if}
          {#if sourceSystem}
            <dt class="text-gray-500">Source System</dt>
            <dd class="text-gray-700">{sourceSystem}</dd>
          {/if}
          {#if publisher}
            <dt class="text-gray-500">Publisher</dt>
            <dd class="text-gray-700 break-all">{publisher}</dd>
          {/if}
        </dl>
      {/if}

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

    {#if activeExistingRequest}
      <div class="ds-card border-blue-200 bg-blue-50 space-y-1">
        <p class="font-medium text-blue-800">Access already requested</p>
        <p class="text-sm text-blue-700">
          Status: <code>{String(activeExistingRequest['status'] ?? '-')}</code>
        </p>
        <a href="/consumer" class="text-sm text-brand-600 hover:underline">View request -></a>
      </div>
    {:else if negotiationResult}
      <div class="ds-card border-green-200 bg-green-50 space-y-1">
        <p class="font-medium text-green-800">Access granted!</p>
        <p class="text-sm text-green-700">Agreement: <code>{negotiationResult.agreementId}</code></p>
        <a href="/consumer" class="text-sm text-brand-600 hover:underline">View active transfers -></a>
      </div>
    {:else}
      <button class="ds-btn-primary" onclick={() => (wizardOpen = true)}>
        Request access
      </button>
    {/if}

    {#if wizardOpen}
      <NegotiationWizard
        assetId={data.assetId}
        counterPartyAddress={negotiation?.counterPartyAddress ?? ''}
        offerId={negotiation?.offerId ?? data.assetId}
        assigner={negotiation?.assigner ?? ''}
        odrlPolicy={negotiation?.odrlPolicy ?? null}
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
