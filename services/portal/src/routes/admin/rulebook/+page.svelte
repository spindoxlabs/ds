<script lang="ts">
  let { data } = $props();

  const roleSections = $derived((data.sections ?? []).filter((section) => ['Roles', 'Participation Policy', 'Onboarding', 'Offboarding and Suspension', 'Revocation Policy'].includes(section.title)));
  const evidenceSection = $derived((data.sections ?? []).find((section) => section.title === 'Evidence'));
</script>

<svelte:head><title>Rulebook</title></svelte:head>

<div class="space-y-6">
  <section class="rounded-3xl border border-slate-200 bg-gradient-to-br from-stone-100 via-white to-emerald-50 p-6 shadow-sm">
    <p class="text-xs font-semibold uppercase tracking-[0.24em] text-emerald-700">Governance Authority</p>
    <h1 class="mt-2 text-3xl font-bold tracking-tight text-slate-950">Dataspace Rulebook</h1>
    <p class="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
      Operational rules for participants, onboarding, suspension, revocation and assessment evidence.
      This page reads the repository rulebook document, so the demo shows the same governance text used by the evidence pack.
    </p>
  </section>

  {#if !data.available}
    <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-800">
      Rulebook not found. Mount <code>docs/rulebook.md</code> into the portal container or set <code>DOCS_PATH</code>.
    </div>
  {:else}
    <section class="grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
      <aside class="space-y-4">
        <article class="ds-card bg-slate-950 text-white">
          <h2 class="text-lg font-bold">Decision model</h2>
          <div class="mt-4 space-y-3 text-sm text-slate-200">
            <p><span class="font-semibold text-white">Admit</span> only with DID, membership VC, role, scope and reachable DSP endpoint.</p>
            <p><span class="font-semibold text-white">Suspend</span> by revoking/suspending VC status and blocking new negotiations.</p>
            <p><span class="font-semibold text-white">Audit</span> through provenance events and evidence reports.</p>
          </div>
        </article>

        {#if evidenceSection}
          <article class="ds-card border-emerald-200 bg-emerald-50">
            <h2 class="text-lg font-bold text-slate-950">Assessment evidence</h2>
            <ul class="mt-3 space-y-2 text-sm text-emerald-950">
              {#each evidenceSection.bullets as bullet}
                <li class="flex gap-2"><span class="text-emerald-600">■</span><span>{bullet}</span></li>
              {/each}
            </ul>
          </article>
        {/if}
      </aside>

      <div class="space-y-4">
        {#each roleSections as section}
          <article class="ds-card">
            <div class="flex items-start justify-between gap-4">
              <h2 class="text-lg font-bold text-slate-950">{section.title}</h2>
              <span class="ds-badge bg-slate-100 text-slate-700">rulebook</span>
            </div>
            {#if section.body}
              <p class="mt-3 text-sm leading-6 text-slate-600">{section.body}</p>
            {/if}
            {#if section.bullets.length}
              <ul class="mt-3 space-y-2 text-sm text-slate-700">
                {#each section.bullets as bullet}
                  <li class="flex gap-2"><span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-900"></span><span>{bullet}</span></li>
                {/each}
              </ul>
            {/if}
          </article>
        {/each}
      </div>
    </section>

    <section class="ds-card bg-slate-50">
      <details>
        <summary class="cursor-pointer text-sm font-semibold text-slate-900">Show raw rulebook Markdown</summary>
        <pre class="mt-4 max-h-[28rem] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">{data.markdown}</pre>
      </details>
    </section>
  {/if}
</div>
