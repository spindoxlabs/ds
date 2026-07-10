<script lang="ts">
  import ConsentBadge from '$lib/components/ConsentBadge.svelte';
  import type { DataShareDecision, OwnedDataset } from '$lib/server/connector';

  let { data, form } = $props();

  const sharesByDataset = $derived(
    new Map((data.shares as DataShareDecision[]).map((share) => [share.dataset_id, share])),
  );

  function decisionFor(dataset: OwnedDataset): DataShareDecision | undefined {
    return sharesByDataset.get(dataset.asset_id) ?? sharesByDataset.get(dataset.name);
  }

  function titleFor(dataset: OwnedDataset): string {
    return dataset.title ?? dataset.name.replaceAll('_', ' ').replaceAll('.', ' / ');
  }
</script>

<svelte:head>
  <title>My Data</title>
</svelte:head>

<div class="max-w-4xl space-y-6">
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

  {#if data.datasets.length === 0 && !data.error}
    <div class="ds-card text-sm text-gray-600">
      No data products are currently mapped to your subject identity.
    </div>
  {:else}
    <div class="grid gap-4">
      {#each data.datasets as dataset}
        {@const decision = decisionFor(dataset)}
        {@const shared = decision?.status === 'granted'}
        <article class="ds-card">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="font-semibold text-gray-900">{titleFor(dataset)}</h2>
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
              </div>
            </div>

            <form method="POST" action={shared ? '?/stop' : '?/share'} class="shrink-0">
              <input type="hidden" name="dataset_id" value={dataset.asset_id} />
              <button type="submit" class={shared ? 'ds-btn-danger text-sm' : 'ds-btn-primary text-sm'}>
                {shared ? 'Disable sharing' : 'Enable sharing'}
              </button>
            </form>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</div>
