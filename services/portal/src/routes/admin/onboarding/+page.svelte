<script lang="ts">
  import type { Agreement, Invite, Owner, OrganizationApplication } from '$lib/server/identity-registry';

  let { data, form } = $props();

  const owners = $derived(
    new Map((data.owners as Owner[]).map((o) => [o.id, o])),
  );

  const FILTERS = [
    { value: 'pending', label: 'Awaiting review' },
    { value: 'verified', label: 'Verified' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'all', label: 'All' },
  ];

  const statusTone: Record<string, string> = {
    pending: 'bg-amber-50 text-amber-800',
    verified: 'bg-emerald-50 text-emerald-700',
    rejected: 'bg-gray-100 text-gray-600',
  };

  /**
   * The registry enforces these gates; the page states them so an operator can
   * see *why* a step is not available rather than finding a button missing.
   */
  function credentialGate(owner: Owner | undefined): string | null {
    if (!owner) return 'No owner record yet — verify the application first.';
    if (owner.status !== 'verified') return `Owner is ${owner.status ?? 'unknown'}, not verified.`;
    if (!owner.agreement_id) return 'No service agreement has been accepted yet.';
    return null;
  }

  function promoteGate(owner: Owner | undefined): string | null {
    const blocked = credentialGate(owner);
    if (blocked) return blocked;
    // The credential itself is checked by the registry — it is not in this
    // projection, so promotion is offered and IR refuses if it is missing.
    return null;
  }
</script>

<svelte:head><title>Organisation onboarding</title></svelte:head>

<div class="space-y-5">
  <div>
    <h1 class="text-xl font-bold text-gray-900">Organisation onboarding</h1>
    <p class="text-sm text-gray-600 mt-1">
      Review applications and take an organisation through to a participant. Each
      action calls the same identity-registry endpoint as <code class="bg-gray-100 px-1 rounded">ir-cli</code>.
    </p>
  </div>

  {#if form?.error}
    <div class="ds-card border-red-200 bg-red-50 text-sm text-red-700">{form.error}</div>
  {/if}
  {#if data.error}
    <div class="ds-card border-amber-200 bg-amber-50 text-sm text-amber-900">{data.error}</div>
  {/if}


  <!-- Invitations: the only way a stranger can file an application. -->
  <section class="ds-card space-y-3">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h2 class="font-semibold text-gray-900">Invitations</h2>
        <p class="text-xs text-gray-600 mt-0.5">
          An organisation needs a code to apply. Send it out of band — the registry
          stores only a hash, so a code is shown once and cannot be looked up again.
        </p>
      </div>
      {#if data.may.write}
        <form method="POST" action="?/invite" class="flex items-end gap-2 shrink-0">
          <label class="text-xs text-gray-600">
            For
            <input class="ds-input mt-1 block w-48" name="label" placeholder="who it is for" />
          </label>
          <label class="text-xs text-gray-600">
            Valid days
            <input class="ds-input mt-1 block w-24" name="ttl_days" type="number" value="30" min="1" />
          </label>
          <button class="ds-btn-secondary text-sm">Issue code</button>
        </form>
      {/if}
    </div>

    {#if form?.issuedCode}
      <div class="border border-emerald-200 bg-emerald-50 rounded-lg p-3 space-y-1">
        <p class="text-xs text-emerald-900">
          Copy this now — it cannot be shown again{#if form.issuedLabel} ({form.issuedLabel}){/if}:
        </p>
        <p class="font-mono text-sm break-all text-emerald-900">{form.issuedCode}</p>
        <p class="text-xs text-emerald-800">
          Send with the link <span class="font-mono">/join?code=…</span>
        </p>
      </div>
    {/if}

    {#if (data.invites as Invite[]).length > 0}
      <table class="w-full text-xs">
        <thead>
          <tr class="text-left text-gray-500 border-b border-gray-200">
            <th class="pb-1 pr-4">For</th>
            <th class="pb-1 pr-4">Issued</th>
            <th class="pb-1 pr-4">Expires</th>
            <th class="pb-1">State</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {#each data.invites as inv (inv.id)}
            <tr>
              <td class="py-1 pr-4">{inv.label ?? '—'}</td>
              <td class="py-1 pr-4 text-gray-600">{new Date(inv.created_at).toLocaleDateString()}</td>
              <td class="py-1 pr-4 text-gray-600">
                {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString() : 'never'}
              </td>
              <td class="py-1">
                {#if inv.redeemed_at}
                  <span class="ds-badge bg-gray-100 text-gray-600">used</span>
                {:else}
                  <span class="ds-badge bg-emerald-50 text-emerald-700">open</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>

  <div class="flex gap-2">
    {#each FILTERS as f}
      <a
        href="?status={f.value}"
        class="ds-badge {data.status === f.value ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-700'}"
      >{f.label}</a>
    {/each}
  </div>

  {#if !data.may.write}
    <p class="text-xs text-gray-500">
      You have read access. Verifying and crediting an organisation needs
      <code class="bg-gray-100 px-1 rounded">identity-registry.organizations.write</code>.
    </p>
  {/if}

  {#if (data.applications as OrganizationApplication[]).length === 0}
    <p class="text-sm text-gray-500 py-6 text-center">No applications in this view.</p>
  {:else}
    <div class="grid gap-3">
      {#each data.applications as app (app.id)}
        {@const owner = owners.get(app.alias)}
        <article class="ds-card space-y-3">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <h2 class="font-semibold text-gray-900">{app.legal_name}</h2>
              <p class="text-xs text-gray-500 font-mono">{app.alias}</p>
            </div>
            <span class="ds-badge {statusTone[app.status] ?? 'bg-gray-100 text-gray-600'}">
              {app.status}
            </span>
          </div>

          <dl class="grid gap-x-6 gap-y-1 text-xs text-gray-600 sm:grid-cols-2">
            {#if app.registration_number}
              <div><dt class="inline text-gray-500">Registration:</dt>
                <dd class="inline"> {app.registration_number} ({app.registration_type ?? 'n/a'})</dd></div>
            {/if}
            {#if app.legal_country_code}
              <div><dt class="inline text-gray-500">Country:</dt>
                <dd class="inline"> {app.legal_country_code}</dd></div>
            {/if}
            <div><dt class="inline text-gray-500">Roles:</dt>
              <dd class="inline"> {app.roles.join(', ')}</dd></div>
            {#if app.did}
              <div class="sm:col-span-2"><dt class="inline text-gray-500">DID:</dt>
                <dd class="inline font-mono break-all"> {app.did}</dd></div>
            {/if}
            {#if app.evidence_ref}
              <div class="sm:col-span-2"><dt class="inline text-gray-500">Evidence:</dt>
                <dd class="inline"> {app.evidence_ref}</dd></div>
            {/if}
            {#if owner?.agreement_id}
              <div class="sm:col-span-2"><dt class="inline text-gray-500">Agreement:</dt>
                <dd class="inline"> {owner.agreement_id}@{owner.agreement_version}
                  ({owner.agreement_capacity})</dd></div>
            {/if}
          </dl>

          {#if app.status === 'pending' && data.may.write}
            <!-- Verification is an offline judgement; the reference is recorded, the
                 document itself never enters the registry. -->
            <form method="POST" action="?/decide" class="flex flex-wrap items-end gap-2">
              <input type="hidden" name="id" value={app.id} />
              <label class="text-xs text-gray-600">
                Evidence reference
                <input class="ds-input mt-1 block w-64" name="evidence_ref"
                       placeholder="ticket or document id" />
              </label>
              <button class="ds-btn-primary text-sm" name="status" value="verified">Verify</button>
              <button class="ds-btn-secondary text-sm" name="status" value="rejected">Reject</button>
            </form>
          {/if}

          {#if app.status === 'verified'}
            <div class="border-t border-gray-100 pt-3 space-y-3">
              <!-- Step 2: the agreement the organisation signed, and in what capacity. -->
              {#if data.may.write && !owner?.agreement_id}
                <form method="POST" action="?/acceptAgreement" class="flex flex-wrap items-end gap-2">
                  <input type="hidden" name="alias" value={app.alias} />
                  <label class="text-xs text-gray-600">
                    Agreement accepted
                    <select class="ds-input mt-1 block w-72" name="agreement">
                      {#each data.agreements as a (a.id + a.version)}
                        <option value="{a.id}@{a.version}">
                          {a.id} @ {a.version}{#if a.capacity} ({a.capacity}){/if}
                        </option>
                      {/each}
                    </select>
                  </label>
                  <button class="ds-btn-secondary text-sm">Record acceptance</button>
                </form>
              {/if}

              <!-- Step 3: the credential. IR refuses unless verified + agreement. -->
              <div class="flex flex-wrap items-center gap-2">
                {#if credentialGate(owner)}
                  <p class="text-xs text-amber-800">
                    Credential cannot be issued: {credentialGate(owner)}
                  </p>
                {:else if data.may.write}
                  <form method="POST" action="?/issueCredential">
                    <input type="hidden" name="alias" value={app.alias} />
                    <button class="ds-btn-secondary text-sm">Issue organisation credential</button>
                  </form>
                {/if}
              </div>

              <!-- Step 4: promotion — the irreversible one. -->
              {#if data.may.promote}
                {#if promoteGate(owner)}
                  <p class="text-xs text-amber-800">Cannot promote: {promoteGate(owner)}</p>
                {:else}
                  <form method="POST" action="?/promote" class="flex flex-wrap items-end gap-2">
                    <input type="hidden" name="alias" value={app.alias} />
                    <label class="text-xs text-gray-600">
                      DSP address
                      <input class="ds-input mt-1 block w-80" name="dsp_address"
                             value={app.dsp_address ?? ''} placeholder="https://…/protocol/2025-1" />
                    </label>
                    <button class="ds-btn-primary text-sm">Promote to participant</button>
                  </form>
                  <p class="text-xs text-gray-500">
                    Promotion registers this organisation as a DSP counterparty other
                    participants will negotiate with.
                  </p>
                {/if}
              {/if}
            </div>
          {/if}
        </article>
      {/each}
    </div>
  {/if}
</div>
