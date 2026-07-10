<script lang="ts">
  let { data } = $props();

  const core = $derived(data.coreCompliance);
  const e2e = $derived(data.coreE2E);
  const coreStatus = $derived(statusLabel(core?.passed));
  const e2eStatus = $derived(statusLabel(undefined, e2e?.status));

  function statusLabel(passed: boolean | undefined, status?: string) {
    if (passed === true || status === 'PASS') return 'PASS';
    if (passed === false || status === 'FAIL') return 'FAIL';
    return 'MISSING';
  }

  function statusClass(label: string) {
    if (label === 'PASS') return 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200';
    if (label === 'FAIL') return 'bg-red-100 text-red-800 ring-1 ring-red-200';
    return 'bg-amber-100 text-amber-800 ring-1 ring-amber-200';
  }

  function fmt(value: string | undefined) {
    return value ? new Date(value).toLocaleString() : 'not generated';
  }
</script>

<svelte:head><title>Compliance Cockpit</title></svelte:head>

<div class="space-y-6">
  <section class="relative overflow-hidden rounded-3xl border border-slate-200 bg-slate-950 p-6 text-white shadow-sm">
    <div class="absolute -right-12 -top-16 h-44 w-44 rounded-full bg-cyan-400/20 blur-2xl"></div>
    <div class="absolute bottom-0 right-24 h-28 w-28 rounded-full bg-emerald-400/20 blur-xl"></div>
    <div class="relative max-w-3xl space-y-3">
      <p class="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200">DSSC evidence cockpit</p>
      <h1 class="text-3xl font-bold tracking-tight">Compliance and governance evidence</h1>
      <p class="text-sm leading-6 text-slate-300">
        This view describes the reusable dataspace core, runtime evidence and production readiness controls.
      </p>
    </div>
  </section>

  <section class="grid gap-4 lg:grid-cols-3">
    <article class="ds-card border-slate-200 bg-gradient-to-br from-white to-slate-50">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-slate-500">Project core</p>
          <h2 class="mt-1 text-lg font-bold text-slate-950">Compliance CI</h2>
        </div>
        <span class="ds-badge {statusClass(coreStatus)}">{coreStatus}</span>
      </div>
      <dl class="mt-5 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt class="text-slate-500">Datasets</dt>
          <dd class="font-semibold text-slate-900">{core?.datasets_checked ?? '—'}</dd>
        </div>
        <div>
          <dt class="text-slate-500">Checks</dt>
          <dd class="font-semibold text-slate-900">{core?.checks?.length ?? '—'}</dd>
        </div>
      </dl>
      <p class="mt-4 text-xs text-slate-500">Generated: {fmt(core?.generated_at)}</p>
    </article>

    <article class="ds-card border-slate-200 bg-gradient-to-br from-white to-slate-50">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-slate-500">Project core</p>
          <h2 class="mt-1 text-lg font-bold text-slate-950">E2E flow</h2>
        </div>
        <span class="ds-badge {statusClass(e2eStatus)}">{e2eStatus}</span>
      </div>
      <dl class="mt-5 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt class="text-slate-500">Steps</dt>
          <dd class="font-semibold text-slate-900">{e2e?.steps?.length ?? '—'}</dd>
        </div>
        <div>
          <dt class="text-slate-500">Profile</dt>
          <dd class="font-semibold text-slate-900">{e2e?.profile ?? 'core'}</dd>
        </div>
      </dl>
      <p class="mt-4 text-xs text-slate-500">Generated: {fmt(e2e?.generated_at)}</p>
    </article>

    <article class="ds-card border-cyan-200 bg-cyan-50">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-widest text-cyan-700">Production profile</p>
          <h2 class="mt-1 text-lg font-bold text-slate-950">Preflight controls</h2>
        </div>
        <span class="ds-badge bg-cyan-100 text-cyan-800 ring-1 ring-cyan-200">CONFIGURED</span>
      </div>
      <ul class="mt-4 space-y-2 text-sm text-cyan-950">
        {#each data.productionChecks as check}
          <li class="flex gap-2"><span class="text-cyan-600">■</span><span>{check}</span></li>
        {/each}
      </ul>
      <p class="mt-4 text-xs text-cyan-800">Run <code>task production:preflight</code> for the executable check.</p>
    </article>
  </section>

  <section class="grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
    <article class="ds-card">
      <div class="flex items-center justify-between gap-4">
        <div>
          <h2 class="text-lg font-bold text-slate-950">Evidence timeline</h2>
          <p class="text-sm text-slate-500">Core runtime flow verified by the latest E2E report.</p>
        </div>
        <a href="/admin/audit" class="ds-btn-secondary">Open audit</a>
      </div>

      {#if e2e?.steps?.length}
        <ol class="mt-5 space-y-3">
          {#each e2e.steps as step, index}
            <li class="grid grid-cols-[2rem_1fr] gap-3">
              <div class="flex flex-col items-center">
                <span class="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">{index + 1}</span>
                {#if index < e2e.steps.length - 1}
                  <span class="mt-1 h-full min-h-6 w-px bg-slate-200"></span>
                {/if}
              </div>
              <div class="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-semibold text-slate-900">{step.name}</span>
                  <span class="ds-badge {statusClass(step.status)}">{step.status}</span>
                </div>
                {#if step.detail}
                  <p class="mt-1 text-sm text-slate-600">{step.detail}</p>
                {/if}
              </div>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="mt-5 rounded-2xl bg-amber-50 p-4 text-sm text-amber-800">
          No E2E report found. Run <code>task compliance:e2e:full</code> and refresh this page.
        </p>
      {/if}
    </article>

    <aside class="space-y-4">
      <article class="ds-card border-slate-300 bg-white text-slate-950">
        <h2 class="text-lg font-bold">Trust status</h2>
        <div class="mt-4 space-y-3 text-sm">
          <div class="flex items-center justify-between gap-3"><span class="text-slate-700">DID documents</span><span class="ds-badge bg-slate-100 text-slate-900 ring-1 ring-slate-200">did:web</span></div>
          <div class="flex items-center justify-between gap-3"><span class="text-slate-700">VC status</span><span class="ds-badge bg-emerald-100 text-emerald-900 ring-1 ring-emerald-200">registry-ready</span></div>
          <div class="flex items-center justify-between gap-3"><span class="text-slate-700">Membership VC</span><span class="ds-badge bg-cyan-100 text-cyan-900 ring-1 ring-cyan-200">wallet-filtered</span></div>
          <div class="flex items-center justify-between gap-3"><span class="text-slate-700">Issuer</span><span class="ds-badge bg-amber-100 text-amber-950 ring-1 ring-amber-200">demo until M9</span></div>
        </div>
      </article>

      <article class="ds-card">
        <h2 class="text-lg font-bold text-slate-950">Evidence files</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div><dt class="text-slate-500">Core compliance</dt><dd class="font-mono text-xs text-slate-700">{data.evidence.coreComplianceMd}</dd></div>
          <div><dt class="text-slate-500">Core DCAT</dt><dd class="font-mono text-xs text-slate-700">{data.evidence.coreDcat}</dd></div>
          <div><dt class="text-slate-500">Core ODRL</dt><dd class="font-mono text-xs text-slate-700">{data.evidence.coreOdrl}</dd></div>
          <div><dt class="text-slate-500">Core E2E</dt><dd class="font-mono text-xs text-slate-700">{data.evidence.coreE2EMd}</dd></div>
        </dl>
      </article>
    </aside>
  </section>
</div>
