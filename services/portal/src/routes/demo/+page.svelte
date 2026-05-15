<script lang="ts">
  let { data, form } = $props();

  const state = $derived(form ?? data);
  const consentId = $derived(state.consentId ?? data.consentId ?? '');
  const status = $derived(state.consentStatus ?? 'not_found');
  const rows = $derived(state.query?.rows ?? []);
  const columns = $derived(rows.length > 0 ? Object.keys(rows[0]).slice(0, 6) : []);

  const steps = $derived([
    { label: 'Request', active: ['pending', 'granted', 'revoked'].includes(status) },
    { label: 'Grant', active: status === 'granted' },
    { label: 'Query', active: rows.length > 0 },
    { label: 'Revoke', active: status === 'revoked' },
  ]);
</script>

<svelte:head>
  <title>Standalone Dataspace Demo</title>
</svelte:head>

<section class="space-y-6">
  <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <h1 class="text-2xl font-semibold text-gray-950">Standalone Dataspace Demo</h1>
      <p class="mt-1 text-sm text-gray-600">
        Visualizza autorizzazione, filtro dati e revoca su dati CELINE o mock.
      </p>
    </div>
    <form method="POST" action="?/clear">
      <button class="ds-btn-secondary" type="submit">Reset</button>
    </form>
  </div>

  {#if state.error}
    <div class="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      {state.error}
    </div>
  {:else if state.message}
    <div class="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
      {state.message}
    </div>
  {/if}

  <div class="grid gap-3 sm:grid-cols-4">
    {#each steps as step, i}
      <div class="rounded-md border p-4 {step.active ? 'border-brand-600 bg-brand-50' : 'border-gray-200 bg-white'}">
        <div class="text-xs font-medium uppercase text-gray-500">Step {i + 1}</div>
        <div class="mt-1 text-lg font-semibold {step.active ? 'text-brand-700' : 'text-gray-500'}">
          {step.label}
        </div>
      </div>
    {/each}
  </div>

  <div class="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
    <section class="ds-card space-y-4">
      <div>
        <h2 class="text-base font-semibold text-gray-900">Controlli</h2>
        <p class="mt-1 text-sm text-gray-600">
          Subject demo: <span class="font-mono">{state.subjectId}</span>
          {#if state.authenticated}
            <span class="ml-2 text-green-700">Keycloak: {state.userName ?? 'logged in'}</span>
          {:else}
            <span class="ml-2 text-amber-700">Keycloak: non autenticato</span>
          {/if}
        </p>
      </div>

      <dl class="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt class="text-gray-500">Dataset</dt>
          <dd class="font-mono text-xs text-gray-900">{state.datasetId}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Consumer</dt>
          <dd class="font-mono text-xs text-gray-900">{state.consumerId}</dd>
        </div>
        <div>
          <dt class="text-gray-500">Consent status</dt>
          <dd class="font-semibold capitalize">{status}</dd>
        </div>
        <div class="col-span-2">
          <dt class="text-gray-500">Consent ID</dt>
          <dd class="break-all font-mono text-xs text-gray-900">{consentId || 'none'}</dd>
        </div>
      </dl>

      <div class="grid gap-2">
        <form method="POST" action="?/request">
          <button class="ds-btn-primary w-full" type="submit">1. Request consent</button>
        </form>
        <form method="POST" action="?/approve">
          <input type="hidden" name="consentId" value={consentId} />
          <button class="ds-btn-primary w-full" type="submit" disabled={!consentId}>2. Grant consent</button>
        </form>
        <form method="POST" action="?/revoke">
          <input type="hidden" name="consentId" value={consentId} />
          <button class="ds-btn-danger w-full" type="submit" disabled={!consentId}>3. Revoke consent</button>
        </form>
      </div>
    </section>

    <section class="ds-card">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h2 class="text-base font-semibold text-gray-900">Query result</h2>
          <p class="mt-1 text-sm text-gray-600">
            L'adapter restituisce righe solo quando il consenso e attivo.
          </p>
        </div>
        <span class="ds-badge {rows.length > 0 ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700'}">
          {rows.length} rows
        </span>
      </div>

      <div class="mt-4 overflow-hidden rounded-md border border-gray-200">
        <table class="min-w-full divide-y divide-gray-200 text-sm">
          <thead class="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              {#if columns.length === 0}
                <th class="px-3 py-2">Result</th>
              {:else}
                {#each columns as column}
                  <th class="px-3 py-2">{column}</th>
                {/each}
              {/if}
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 bg-white">
            {#if rows.length === 0}
              <tr>
                <td colspan={Math.max(columns.length, 1)} class="px-3 py-8 text-center text-gray-500">No authorized rows</td>
              </tr>
            {:else}
              {#each rows as row}
                <tr>
                  {#each columns as column}
                    <td class="px-3 py-2 font-mono text-xs">{String(row[column] ?? '')}</td>
                  {/each}
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>

      <pre class="mt-4 max-h-56 overflow-auto rounded-md bg-gray-950 p-3 text-xs text-gray-100">{JSON.stringify(state.query?.authorization ?? {}, null, 2)}</pre>
    </section>
  </div>
</section>
