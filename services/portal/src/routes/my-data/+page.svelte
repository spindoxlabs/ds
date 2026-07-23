<script lang="ts">
  import ConsentBadge from '$lib/components/ConsentBadge.svelte';
  import type { DataShareDecision, OwnedDataset, SharingOffer } from '$lib/server/connector';

  let { data, form } = $props();

  const sharesByDataset = $derived(
    new Map((data.shares as DataShareDecision[]).map((share) => [share.dataset_id, share])),
  );

  const sharesByOffer = $derived(
    new Map(
      (data.shares as DataShareDecision[])
        .filter((share) => share.offer_id)
        .map((share) => [share.offer_id as string, share]),
    ),
  );

  function decisionFor(dataset: OwnedDataset): DataShareDecision | undefined {
    return sharesByDataset.get(dataset.asset_id) ?? sharesByDataset.get(dataset.name);
  }

  function titleFor(dataset: OwnedDataset): string {
    return dataset.title ?? dataset.name.replaceAll('_', ' ').replaceAll('.', ' / ');
  }

  // ds serves ISO 8601 codes; rendering them as sentences is the frontend's job.
  // An unmapped code degrades to the code itself rather than disappearing.
  const DURATION_LABELS: Record<string, string> = {
    PT15M: 'every 15 minutes',
    PT1H: 'hourly',
    P1D: 'daily',
    P1Y: '1 year',
    P2Y: '2 years',
    P5Y: '5 years',
  };

  function duration(code: string | null): string {
    if (!code) return '—';
    return DURATION_LABELS[code] ?? code;
  }

  function coverage(offer: SharingOffer): string {
    const parts: string[] = [];
    if (offer.coverage.retrospective) parts.push(`the past ${duration(offer.coverage.retrospective)}`);
    if (offer.coverage.prospective) parts.push(`the next ${duration(offer.coverage.prospective)}`);
    return parts.length ? parts.join(' and ') : 'no defined window';
  }
</script>

<svelte:head>
  <title>My Data</title>
</svelte:head>

<div class="max-w-4xl space-y-8">
  <div class="flex flex-col gap-1">
    <h1 class="text-2xl font-bold text-gray-900">My Data</h1>
    <p class="text-sm text-gray-600">
      Subject identity: <code>{data.subjectId}</code>
    </p>
  </div>

  {#if data.error}
    <div class="ds-card border-red-200 bg-red-50 text-sm text-red-700">{data.error}</div>
  {/if}

  {#if form?.error}
    <div class="ds-card border-red-200 bg-red-50 text-sm text-red-700">{form.error}</div>
  {/if}

  <!-- What you are actually asked about: purpose-scoped bundles, not datasets. -->
  <section class="space-y-4">
    <div>
      <h2 class="text-lg font-semibold text-gray-900">Sharing</h2>
      <p class="text-sm text-gray-600">
        What your data may be used for, by whom, and for how long.
      </p>
    </div>

    {#if data.offersError}
      <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-800">
        {data.offersError}
      </div>
    {:else if data.offers.length === 0}
      <div class="ds-card text-sm text-gray-600">No sharing offers are published.</div>
    {:else}
      <div class="grid gap-4">
        {#each data.offers as offer (offer.id)}
          {@const decision = sharesByOffer.get(offer.id)}
          {@const shared = decision?.status === 'granted'}
          <article class="ds-card">
            <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0 space-y-2">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="font-semibold text-gray-900">
                    {offer.fallback_text_en.purpose_label}
                  </h3>
                  {#if !offer.requires_consent}
                    <span class="ds-badge bg-slate-100 text-slate-700">required by contract</span>
                  {:else if decision}
                    <ConsentBadge status={decision.status} />
                  {:else}
                    <span class="ds-badge bg-gray-100 text-gray-600">not shared</span>
                  {/if}
                </div>

                {#if offer.fallback_text_en.purpose_definition}
                  <p class="text-sm text-gray-700">{offer.fallback_text_en.purpose_definition}</p>
                {/if}

                <dl class="grid gap-x-6 gap-y-1 text-sm text-gray-600 sm:grid-cols-2">
                  <div>
                    <dt class="inline font-medium text-gray-700">Who receives it:</dt>
                    <dd class="inline">
                      {offer.recipients.controller}{#if offer.recipients.controller_role}
                        ({offer.recipients.controller_role}){/if}
                      and {offer.fallback_text_en.processor_category}
                    </dd>
                  </div>
                  <div>
                    <dt class="inline font-medium text-gray-700">What:</dt>
                    <dd class="inline">{offer.measures.join(', ') || '—'}</dd>
                  </div>
                  <div>
                    <dt class="inline font-medium text-gray-700">How often:</dt>
                    <dd class="inline">{duration(offer.resolution)}</dd>
                  </div>
                  <div>
                    <dt class="inline font-medium text-gray-700">Which period:</dt>
                    <dd class="inline">{coverage(offer)}</dd>
                  </div>
                  <div>
                    <dt class="inline font-medium text-gray-700">Kept for:</dt>
                    <dd class="inline">{duration(offer.retention)}</dd>
                  </div>
                  <div>
                    <dt class="inline font-medium text-gray-700">Scope:</dt>
                    <dd class="inline">{offer.subject_scope.replaceAll('_', ' ')}</dd>
                  </div>
                </dl>
              </div>

              {#if offer.requires_consent}
                <form method="POST" action="?/shareOffer" class="shrink-0">
                  <input type="hidden" name="offer_id" value={offer.id} />
                  <input type="hidden" name="enabled" value={shared ? 'false' : 'true'} />
                  <button
                    type="submit"
                    class={shared ? 'ds-btn-danger text-sm' : 'ds-btn-primary text-sm'}
                  >
                    {shared ? 'Stop sharing' : 'Share'}
                  </button>
                </form>
              {:else}
                <!-- Contract-based processing is disclosed, not toggled: offering
                     a choice that does not exist is what invalidates consent. -->
                <p class="shrink-0 text-xs text-gray-500 sm:w-32 sm:text-right">
                  No choice to make — this is part of your membership agreement.
                </p>
              {/if}
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Detail view: the datasets that actually hold rows for this subject. -->
  <section class="space-y-4">
    <div>
      <h2 class="text-lg font-semibold text-gray-900">Data held about you</h2>
      <p class="text-sm text-gray-600">
        The individual datasets your identity appears in. Sharing decisions are made above.
      </p>
    </div>

    {#if data.datasets.length === 0 && !data.error}
      <div class="ds-card text-sm text-gray-600">
        No data products are currently mapped to your subject identity.
      </div>
    {:else}
      <div class="grid gap-4">
        {#each data.datasets as dataset}
          {@const decision = decisionFor(dataset)}
          <article class="ds-card">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-semibold text-gray-900">{titleFor(dataset)}</h3>
                {#if decision}
                  <ConsentBadge status={decision.status} />
                {:else}
                  <span class="ds-badge bg-gray-100 text-gray-600">not shared</span>
                {/if}
              </div>
              <p class="mt-1 break-all text-sm text-gray-600">{dataset.asset_id}</p>
              <div class="mt-3 flex flex-wrap gap-2 text-xs text-gray-600">
                <span class="ds-badge bg-blue-50 text-blue-700">{dataset.source ?? 'local'}</span>
                <span class="ds-badge bg-gray-100 text-gray-700">
                  owner column: {dataset.subject_column ?? 'n/a'}
                </span>
                <span class="ds-badge bg-gray-100 text-gray-700">
                  sample rows: {dataset.sample_rows ?? 0}
                </span>
                {#if decision?.purpose?.length}
                  <span class="ds-badge bg-emerald-50 text-emerald-700">
                    purpose: {decision.purpose.join(', ')}
                  </span>
                {/if}
              </div>
            </div>
          </article>
        {/each}
      </div>
    {/if}
  </section>
</div>
