<script lang="ts">
  let { data, form } = $props();
  // Re-fill the form after a rejection so an applicant does not retype everything.
  const values = $derived((form?.values ?? {}) as Record<string, string | undefined>);
  const v = (name: string) => values[name] ?? '';
</script>

<svelte:head><title>Apply to join</title></svelte:head>

<div class="max-w-2xl mx-auto py-8 space-y-5">
  {#if form?.submitted}
    <div class="ds-card border-emerald-200 bg-emerald-50 space-y-2">
      <h1 class="font-semibold text-emerald-900">Application received</h1>
      <p class="text-sm text-emerald-900">
        <span class="font-mono">{form.alias}</span> has been filed for review. An
        operator verifies the details offline and will be in touch — there is
        nothing further to do here, and no status to check.
      </p>
    </div>
  {:else}
    <div>
      <h1 class="text-xl font-bold text-gray-900">Apply to join the dataspace</h1>
      <p class="text-sm text-gray-600 mt-1">
        You need an invitation code from the operator. What you enter is a claim
        about your organisation: it is verified offline before anything is granted.
      </p>
    </div>

    {#if form?.error}
      <div class="ds-card border-red-200 bg-red-50 text-sm text-red-700">{form.error}</div>
    {/if}

    <form method="POST" class="ds-card space-y-4">
      <label class="block text-sm text-gray-700">
        Invitation code
        <input class="ds-input mt-1 w-full" name="invite_code" required
               value={v('invite_code') || data.prefilledCode} />
      </label>

      <div class="grid sm:grid-cols-2 gap-4">
        <label class="block text-sm text-gray-700">
          Legal name
          <input class="ds-input mt-1 w-full" name="legal_name" required value={v('legal_name')} />
        </label>
        <label class="block text-sm text-gray-700">
          Short name
          <input class="ds-input mt-1 w-full" name="alias" required
                 pattern="[a-z0-9][a-z0-9\-]*[a-z0-9]" value={v('alias')} />
          <span class="text-xs text-gray-500">lower-case letters, digits and hyphens</span>
        </label>
        <label class="block text-sm text-gray-700">
          Registration number
          <input class="ds-input mt-1 w-full" name="registration_number" value={v('registration_number')} />
        </label>
        <label class="block text-sm text-gray-700">
          Registration type
          <input class="ds-input mt-1 w-full" name="registration_type"
                 placeholder="e.g. vatID" value={v('registration_type')} />
        </label>
        <label class="block text-sm text-gray-700">
          Country
          <input class="ds-input mt-1 w-full" name="legal_country_code"
                 placeholder="IT" value={v('legal_country_code')} />
        </label>
        <label class="block text-sm text-gray-700">
          DSP address (if you already run a connector)
          <input class="ds-input mt-1 w-full" name="dsp_address" value={v('dsp_address')} />
        </label>
      </div>

      <label class="block text-sm text-gray-700">
        Evidence reference
        <input class="ds-input mt-1 w-full" name="evidence_ref" value={v('evidence_ref')} />
        <span class="text-xs text-gray-500">
          A ticket or document id the operator can look up. Do not attach documents —
          none are stored here.
        </span>
      </label>

      <label class="block text-sm text-gray-700">
        Anything else
        <textarea class="ds-input mt-1 w-full" name="notes" rows="3">{v('notes')}</textarea>
      </label>

      <button class="ds-btn-primary text-sm" type="submit">Send application</button>
    </form>
  {/if}
</div>
