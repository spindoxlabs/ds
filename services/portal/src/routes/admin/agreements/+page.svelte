<script lang="ts">
  import type { Agreement, AgreementAcceptance } from '$lib/server/identity-registry';

  let { data } = $props();

  const byId = $derived.by(() => {
    // Rebuilt in full whenever the loader data changes and never mutated after,
    // so a reactive Map would add tracking for writes that do not happen.
    // eslint-disable-next-line svelte/prefer-svelte-reactivity
    const map = new Map<string, Agreement[]>();
    for (const a of data.agreements as Agreement[]) {
      map.set(a.id, [...(map.get(a.id) ?? []), a]);
    }
    return map;
  });
</script>

<svelte:head><title>Service agreements</title></svelte:head>

<div class="space-y-5">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Service agreements</h1>
    <p class="text-sm text-gray-600 mt-1">
      What participants signed, and in which capacity. Capacity decides whether a
      requesting party is treated as a processor of the controller or as an
      independent controller — which is what makes a consent question necessary
      or redundant.
    </p>
  </div>

  {#if data.error}
    <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-900">{data.error}</div>
  {:else if byId.size === 0}
    <p class="text-sm text-gray-500 py-6 text-center">No agreements are seeded.</p>
  {:else}
    <div class="grid gap-3">
      {#each [...byId.entries()] as [id, versions] (id)}
        {@const accepted = (data.acceptances[id] ?? []) as AgreementAcceptance[]}
        <article class="ds-card space-y-3">
          <div>
            <h2 class="font-semibold text-gray-900">{versions[0].title ?? id}</h2>
            <p class="text-xs text-gray-500 font-mono">{id}</p>
          </div>

          <div class="flex flex-wrap gap-2">
            {#each versions as v (v.version)}
              <span class="ds-badge bg-gray-100 text-gray-700">
                v{v.version}{#if v.capacity} · {v.capacity}{/if}
              </span>
            {/each}
          </div>

          {#if accepted.length === 0}
            <p class="text-xs text-gray-500">Nobody has accepted this agreement yet.</p>
          {:else}
            <table class="w-full text-xs">
              <thead>
                <tr class="text-left text-gray-500 border-b border-gray-200">
                  <th class="pb-1 pr-4">Organisation</th>
                  <th class="pb-1 pr-4">Version</th>
                  <th class="pb-1 pr-4">Accepted</th>
                  <th class="pb-1">By</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                {#each accepted as a (a.owner_alias + a.version)}
                  <tr>
                    <td class="py-1 pr-4 font-mono">{a.owner_alias}</td>
                    <td class="py-1 pr-4">v{a.version}</td>
                    <td class="py-1 pr-4 text-gray-600">
                      {a.accepted_at ? new Date(a.accepted_at).toLocaleDateString() : '—'}
                    </td>
                    <td class="py-1 text-gray-600">{a.accepted_by ?? '—'}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </article>
      {/each}
    </div>
  {/if}
</div>
